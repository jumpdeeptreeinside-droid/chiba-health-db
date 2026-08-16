"""
地域医療スポッター 記事ドラフト自動生成スクリプト
GitHub Actions の weekly_article.yml から実行される。

処理フロー:
  1. vol_state.json から次のVol番号・圏域を取得
  2. SQLite から圏域の薬局統計を取得
  3. Claude API でドラフトを生成
  4. output/<date>_spotter_vol<N>_draft.md に書き出す
  5. vol_state.json を更新

環境変数:
  ANTHROPIC_API_KEY  ... Claude API キー（GitHub Secrets）
"""

import json
import os
import sqlite3
import datetime
from pathlib import Path

import anthropic

ROOT       = Path(__file__).parent.parent
DB_PATH    = ROOT / "data" / "chiba_iryo.db"
STATE_PATH = Path(__file__).parent / "vol_state.json"
TEMPLATE   = Path(__file__).parent / "templates" / "vol_template.md"
OUTPUT_DIR = ROOT / "output"


# ── DB クエリ ────────────────────────────────────────────────

def get_region_stats(conn: sqlite3.Connection, region: str) -> dict:
    """圏域全体の薬局統計"""
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN ds_only=0 THEN 1 ELSE 0 END) as dispensing,
            SUM(CASE WHEN zaitaku_flag=1 AND ds_only=0 THEN 1 ELSE 0 END) as zaitaku,
            ROUND(100.0 * SUM(CASE WHEN zaitaku_flag=1 AND ds_only=0 THEN 1 ELSE 0 END)
                  / NULLIF(SUM(CASE WHEN ds_only=0 THEN 1 ELSE 0 END), 0), 1) as zaitaku_rate
        FROM pharmacies WHERE iryo_ken = ?
    """, (region,))
    row = cur.fetchone()
    return {"total": row[0], "dispensing": row[1],
            "zaitaku": row[2], "zaitaku_rate": row[3]}


def get_city_stats(conn: sqlite3.Connection, region: str) -> list[dict]:
    """市区町村別の薬局統計（addressから市区町村名を抽出）"""
    import re
    cur = conn.cursor()
    cur.execute("""
        SELECT
            address,
            ds_only,
            zaitaku_flag
        FROM pharmacies
        WHERE iryo_ken = ?
    """, (region,))
    rows = cur.fetchall()

    # addressから市区町村名を抽出（例：「千葉県市原市中...」→「市原市」）
    city_map: dict[str, dict] = {}
    for address, ds_only, zaitaku_flag in rows:
        m = re.search(r'(?:千葉県)?(.+?[市区町村])', str(address or ""))
        city = m.group(1) if m else "不明"
        if city not in city_map:
            city_map[city] = {"dispensing": 0, "zaitaku": 0}
        if not ds_only:
            city_map[city]["dispensing"] += 1
            if zaitaku_flag:
                city_map[city]["zaitaku"] += 1

    result = []
    for city, d in sorted(city_map.items(), key=lambda x: -x[1]["dispensing"]):
        dispensing = d["dispensing"]
        zaitaku = d["zaitaku"]
        rate = round(100.0 * zaitaku / dispensing, 1) if dispensing else 0
        result.append({"city": city, "dispensing": dispensing,
                        "zaitaku": zaitaku, "zaitaku_rate": rate})
    return result


def get_pref_zaitaku_rate(conn: sqlite3.Connection) -> float:
    """千葉県全体の在宅対応率"""
    cur = conn.cursor()
    cur.execute("""
        SELECT ROUND(100.0 * SUM(CASE WHEN zaitaku_flag=1 AND ds_only=0 THEN 1 ELSE 0 END)
               / NULLIF(SUM(CASE WHEN ds_only=0 THEN 1 ELSE 0 END), 0), 1)
        FROM pharmacies
    """)
    return cur.fetchone()[0]


def search_pdf_text(conn: sqlite3.Connection, region: str, limit: int = 15) -> list[dict]:
    """SQLite FTS5 で圏域関連テキストを全文検索"""
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT d.filename, p.page_num, p.text
            FROM pages_fts f
            JOIN pages p ON p.id = f.rowid
            JOIN documents d ON d.id = p.doc_id
            WHERE pages_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (region, limit))
        return [{"filename": r[0], "page": r[1], "text": r[2][:600]} for r in cur.fetchall()]
    except Exception:
        pass
    try:
        # FTS5テーブルが存在しない場合はLIKEフォールバック
        cur.execute("""
            SELECT d.filename, p.page_num, p.text
            FROM pages p JOIN documents d ON d.id = p.doc_id
            WHERE p.text LIKE ?
            LIMIT ?
        """, (f"%{region}%", limit))
        return [{"filename": r[0], "page": r[1], "text": r[2][:600]} for r in cur.fetchall()]
    except Exception:
        return []


# ── プロンプト構築 ────────────────────────────────────────────

def build_prompt(vol_num: int, region: str, next_region: str,
                 stats: dict, city_stats: list, pref_rate: float,
                 pdf_excerpts: list, template: str) -> str:
    city_table = "\n".join(
        f"  {r['city']}: 調剤{r['dispensing']}件 / 在宅対応{r['zaitaku']}件 / 在宅対応率{r['zaitaku_rate']}%"
        for r in city_stats
    )
    excerpts_text = "\n\n".join(
        f"【{e['filename']} p.{e['page']}】\n{e['text']}" for e in pdf_excerpts[:10]
    )

    return f"""あなたは千葉県の地域医療を専門とする医療ライター「鷹見ジン」として、
「地域医療スポッター Vol.{vol_num:02d}」の記事ドラフトを日本語で書いてください。

## 対象圏域
{region}医療圏

## CrossHealth 薬局DBデータ（2025年12月時点）
【圏域全体】
- 調剤薬局数: {stats['dispensing']} 件
- 在宅対応薬局数: {stats['zaitaku']} 件
- 在宅対応率: {stats['zaitaku_rate']}%（千葉県全体: {pref_rate}%）

【市区町村別】
{city_table}

## 千葉県保健医療計画 PDF 関連箇所（抜粋）
以下のデータはPDFから抽出したものです。数字はそのまま使用してください。
{excerpts_text}

## 記事テンプレート
{template}

## 執筆指示
- テンプレートの {{{{NUM}}}} → {vol_num:02d}、{{{{NEXT_NUM}}}} → {vol_num+1:02d}、
  {{{{圏域名}}}} → {region} に置き換えてください
- データの数字は上記から引用し、推測で補わないでください
- PDFから確認できなかった数値は「要ファクトチェック」と明記してください
- トーン: 「頼れる先輩薬剤師が話しかける」感じ。難しい言葉は使わない
- 次回予告は「Vol.{vol_num+1:02d}：{next_region}圏域」にしてください
- 文字数目安: 2,000〜3,000字
"""


# ── メイン ────────────────────────────────────────────────────

def main():
    # vol_state.json 読み込み
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    vol_num = state["next_vol"]
    schedule = state["vol_schedule"].get(str(vol_num))
    if not schedule:
        # 🔴 ここに来る理由は2つあって、意味がまったく違う。読んだ人が5秒で分かるように分ける。
        #   ①予定していた号を出し切った（＝故障ではない。次に何を出すかの編集判断が要る）
        #   ②予定表の登録漏れ（＝設定ミス）
        planned = sorted(int(k) for k in state["vol_schedule"])
        done = sorted(state.get("completed_vols", []))
        if planned and done and max(planned) < vol_num and set(planned) <= set(done):
            print(f"[DONE] 予定していた Vol.{min(planned)}〜Vol.{max(planned)} は"
                  f"すべて発行済みです（completed_vols={done}）。"
                  f"Vol.{vol_num} は予定表にありません＝シリーズが完結しています。")
            print("[NEXT] 続けるなら vol_state.json の vol_schedule に次の号を足してください。"
                  "続けないなら .github/workflows の週次スケジュールを止めてください。"
                  "このまま放置すると毎週この失敗が積み上がります。")
        else:
            print(f"[ERROR] Vol.{vol_num} のスケジュールが vol_state.json に未登録です"
                  f"（予定表にある号: {planned} / 発行済み: {done}）")
        return

    region = schedule["region"]
    next_schedule = state["vol_schedule"].get(str(vol_num + 1), {})
    next_region = next_schedule.get("region", "次回圏域")
    today = datetime.date.today().strftime("%Y%m%d")

    print(f"[START] Vol.{vol_num:02d} {region}圏域 ドラフト生成")

    # DB からデータ取得
    conn = sqlite3.connect(DB_PATH)
    stats      = get_region_stats(conn, region)
    city_stats = get_city_stats(conn, region)
    pref_rate  = get_pref_zaitaku_rate(conn)
    excerpts   = search_pdf_text(conn, region)
    conn.close()

    print(f"  薬局統計: {stats['dispensing']}件 / 在宅対応率{stats['zaitaku_rate']}%")
    print(f"  PDF抽出: {len(excerpts)}件")

    # Claude API でドラフト生成
    template = TEMPLATE.read_text(encoding="utf-8")
    prompt   = build_prompt(vol_num, region, next_region,
                            stats, city_stats, pref_rate, excerpts, template)

    client  = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    draft = message.content[0].text

    # ファイル書き出し
    OUTPUT_DIR.mkdir(exist_ok=True)
    filename = f"{today}_spotter_vol{vol_num:02d}_draft.md"
    (OUTPUT_DIR / filename).write_text(draft, encoding="utf-8")
    print(f"[OK] ドラフト生成完了: output/{filename}")

    # vol_state.json 更新
    state["completed_vols"].append(vol_num)
    state["next_vol"] = vol_num + 1
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] vol_state.json 更新: next_vol = {vol_num + 1}")

    # GitHub Actions 用出力変数
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"vol_num={vol_num:02d}\n")
            f.write(f"region={region}\n")
            f.write(f"draft_filename={filename}\n")
            f.write(f"draft_date={today}\n")
    else:
        print(f"vol_num={vol_num:02d}, region={region}, filename={filename}")


if __name__ == "__main__":
    main()

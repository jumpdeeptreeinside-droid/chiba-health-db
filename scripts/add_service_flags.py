"""
薬局サービス特性フラグを pharmacies テーブルに追加するスクリプト
データソース: 関東信越厚生局 施設基準届出受理状況 (r0803)

追加するフラグ:
  mukin_flag       無菌製剤処理加算（無菌室・クリーンルーム保有）
  mayaku_iv_flag   在宅患者医療用麻薬持続注射療法加算（がん疼痛管理等）
  tpn_flag         在宅中心静脈栄養法加算（TPN対応）
  kakari_flag      かかりつけ薬剤師指導料・包括管理料
  renkei_flag      連携強化加算（医療機関との連携体制）
  chiiki_shien_flag 地域支援体制加算（1〜4いずれか）
  iryo_dx_flag     医療ＤＸ推進体制整備加算
  kouhatsu_flag    後発医薬品調剤体制加算（1〜3いずれか）
  tokubetsu_flag   特別調剤基本料Ａ（門内薬局相当の可能性）
  tokutei_kanri_flag 特定薬剤管理指導加算２（ハイリスク薬）
"""

import sqlite3
import unicodedata
import re
import openpyxl
from pathlib import Path

ROOT    = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "chiba_iryo.db"
EXCEL_PATH = Path(r"C:\Users\jumpd\chiba_pdf_db\shisetsu_yakkyoku_r0803\12届出受理医療機関名簿（薬局）千葉r0803.xlsx")

# 届出名称 → フラグ列のマッピング
TODOKE_TO_FLAG = {
    "無菌製剤処理加算":                          "mukin_flag",
    "在宅患者医療用麻薬持続注射療法加算":          "mayaku_iv_flag",
    "在宅中心静脈栄養法加算":                     "tpn_flag",
    "かかりつけ薬剤師指導料及びかかりつけ薬剤師包括管理料": "kakari_flag",
    "連携強化加算":                               "renkei_flag",
    "地域支援体制加算１":                         "chiiki_shien_flag",
    "地域支援体制加算２":                         "chiiki_shien_flag",
    "地域支援体制加算３":                         "chiiki_shien_flag",
    "地域支援体制加算４":                         "chiiki_shien_flag",
    "医療ＤＸ推進体制整備加算":                    "iryo_dx_flag",
    "後発医薬品調剤体制加算１":                    "kouhatsu_flag",
    "後発医薬品調剤体制加算２":                    "kouhatsu_flag",
    "後発医薬品調剤体制加算３":                    "kouhatsu_flag",
    "特別調剤基本料Ａ":                           "tokubetsu_flag",
    "特定薬剤管理指導加算２":                      "tokutei_kanri_flag",
}

ALL_FLAGS = sorted(set(TODOKE_TO_FLAG.values()))


def normalize(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = re.sub(r"[\s　]+", "", text)
    return text.lower()


def load_shisetsu_data() -> dict:
    """
    Excelから施設基準届出データを読み込む
    Returns: {正規化名称: {flag_name: bool, ...}}
    """
    wb = openpyxl.load_workbook(str(EXCEL_PATH), read_only=True, data_only=True)
    ws = wb.active

    # 医療機関番号 → フラグセット
    ika_flags: dict[str, set] = {}
    # 医療機関番号 → 名前・住所
    ika_info: dict[str, dict] = {}

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < 4:
            continue
        if not row[0]:
            continue
        ika_num = str(row[4]).strip() if row[4] else ""
        name    = str(row[7]).strip() if row[7] else ""
        address = str(row[9]).strip() if row[9] else ""
        todoke  = str(row[13]).strip() if row[13] else ""

        if not ika_num:
            continue

        if ika_num not in ika_info and name:
            ika_info[ika_num] = {"name": name, "address": address}

        flag_col = TODOKE_TO_FLAG.get(todoke)
        if flag_col:
            ika_flags.setdefault(ika_num, set()).add(flag_col)

    wb.close()

    # 正規化名称 → フラグdict に変換
    result: dict[str, dict] = {}
    for ika_num, info in ika_info.items():
        norm = normalize(info["name"])
        flags = ika_flags.get(ika_num, set())
        flag_dict = {f: 1 for f in flags}
        # 同名が複数ある場合はフラグをマージ
        if norm in result:
            for k, v in flag_dict.items():
                result[norm][k] = max(result[norm].get(k, 0), v)
        else:
            result[norm] = {"name": info["name"], "address": info["address"], **flag_dict}

    print(f"施設基準届出 薬局数: {len(ika_info)}")
    for flag in ALL_FLAGS:
        cnt = sum(1 for ika_num, flags in ika_flags.items() if flag in flags)
        print(f"  {flag}: {cnt}件")
    return result


def add_columns(conn: sqlite3.Connection):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(pharmacies)").fetchall()]
    for flag in ALL_FLAGS:
        if flag not in cols:
            conn.execute(f"ALTER TABLE pharmacies ADD COLUMN {flag} INTEGER DEFAULT 0")
            print(f"  列追加: {flag}")
    conn.commit()


def match_and_update(conn: sqlite3.Connection, shisetsu: dict) -> int:
    db_rows = conn.execute("SELECT id, name FROM pharmacies").fetchall()

    updates: list[tuple] = []
    matched_exact = 0
    matched_partial = 0

    for pid, db_name in db_rows:
        norm_db = normalize(db_name)

        # 1. 完全一致
        if norm_db in shisetsu:
            info = shisetsu[norm_db]
            row = tuple(info.get(f, 0) for f in ALL_FLAGS) + (pid,)
            updates.append(row)
            matched_exact += 1
            continue

        # 2. 部分一致（どちらかが他方を含む）
        for norm_s, info in shisetsu.items():
            if norm_db in norm_s or norm_s in norm_db:
                row = tuple(info.get(f, 0) for f in ALL_FLAGS) + (pid,)
                updates.append(row)
                matched_partial += 1
                break

    set_clause = ", ".join(f"{f}=?" for f in ALL_FLAGS)
    conn.executemany(
        f"UPDATE pharmacies SET {set_clause} WHERE id=?",
        updates
    )
    conn.commit()

    print(f"\n=== マッチング結果 ===")
    print(f"  完全一致: {matched_exact}件")
    print(f"  部分一致: {matched_partial}件")
    print(f"  合計更新: {len(updates)}件")
    return len(updates)


def print_stats(conn: sqlite3.Connection):
    print("\n=== フラグ別集計 ===")
    for flag in ALL_FLAGS:
        cnt = conn.execute(f"SELECT COUNT(*) FROM pharmacies WHERE {flag}=1").fetchone()[0]
        print(f"  {flag}: {cnt}件")

    print("\n=== 圏域別 無菌製剤処理対応率 ===")
    rows = conn.execute("""
        SELECT iryo_ken, COUNT(*) total, SUM(mukin_flag) mukin,
               SUM(tpn_flag) tpn, SUM(mayaku_iv_flag) mayaku_iv
        FROM pharmacies WHERE ds_only=0
        GROUP BY iryo_ken ORDER BY iryo_ken
    """).fetchall()
    for ken, total, mukin, tpn, mayaku_iv in rows:
        print(f"  {ken:12s}: 無菌={mukin or 0}  TPN={tpn or 0}  麻薬IV={mayaku_iv or 0}  / 計{total}局")


def main():
    print("=== 薬局サービス特性フラグ追加 ===\n")

    print("[1] 施設基準届出データ読み込み...")
    shisetsu = load_shisetsu_data()

    conn = sqlite3.connect(DB_PATH)

    print("\n[2] 列追加...")
    add_columns(conn)

    print("\n[3] 名前マッチング・更新...")
    match_and_update(conn, shisetsu)

    print_stats(conn)
    conn.close()
    print("\n[完了]")


if __name__ == "__main__":
    main()

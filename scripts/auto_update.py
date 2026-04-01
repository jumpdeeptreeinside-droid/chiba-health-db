"""
データ自動更新スクリプト
GitHub Actions の monthly_update.yml から実行される。

処理フロー:
  1. 施設基準届出（関東信越厚生局）の最新版を確認・DL・更新
  2. GMIS薬局機能情報の最新版を確認（新版があれば通知のみ）
  3. data_versions.json を更新
  4. 更新結果を GitHub Actions 出力 & todo.md 向けサマリー生成

令和年月変換:
  令和年 = 西暦年 - 2018  (例: 2026年 → 令和8年 → "08")
  バージョン文字列 "r0803" = 令和8年3月
"""

import json
import os
import io
import sqlite3
import zipfile
import datetime
import unicodedata
import re
import tempfile
from pathlib import Path

import requests

ROOT       = Path(__file__).parent.parent
DB_PATH    = ROOT / "data" / "chiba_iryo.db"
VERSIONS   = ROOT / "data" / "data_versions.json"

SHISETSU_BASE = "https://kouseikyoku.mhlw.go.jp/kantoshinetsu/shisetsu_yakkyoku_{ver}.zip"
GMIS_BASE     = "https://www.mhlw.go.jp/content/11121000/05_pharmacy_{date}.zip"

# 施設基準届出 → フラグ列のマッピング（add_service_flags.py と同じ）
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


# ── ユーティリティ ────────────────────────────────────────────

def wareki_ver(dt: datetime.date) -> str:
    """datetime → 令和年月文字列 (例: 2026-03 → 'r0803')"""
    reiwa_year = dt.year - 2018
    return f"r{reiwa_year:02d}{dt.month:02d}"


def normalize(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = re.sub(r"[\s　]+", "", text)
    return text.lower()


def load_versions() -> dict:
    return json.loads(VERSIONS.read_text(encoding="utf-8"))


def save_versions(v: dict):
    VERSIONS.write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 施設基準届出 更新 ─────────────────────────────────────────

def try_download(url: str) -> bytes | None:
    """URL をダウンロード。404等はNoneを返す"""
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return r.content
        return None
    except Exception:
        return None


def find_latest_shisetsu(current_ver: str) -> tuple[str, str] | None:
    """
    current_ver より新しい施設基準届出を探す
    Returns (version_str, url) or None
    """
    today = datetime.date.today()
    # 今月から遡って3ヶ月分を試す（当月・先月・先々月）
    candidates = []
    for delta in range(0, 4):
        m = today.month - delta
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        candidates.append(wareki_ver(datetime.date(y, m, 1)))

    for ver in candidates:
        if ver <= current_ver:
            continue  # 現在以前はスキップ
        url = SHISETSU_BASE.format(ver=ver)
        print(f"  試行: {url}")
        data = try_download(url)
        if data:
            return ver, url, data
    return None


def update_service_flags(excel_bytes: bytes, conn: sqlite3.Connection):
    """Excelバイト列からサービスフラグを更新"""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), read_only=True, data_only=True)
    ws = wb.active

    # 医療機関番号 → フラグセット
    ika_flags: dict[str, set] = {}
    ika_info:  dict[str, dict] = {}

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < 4:
            continue
        if not row[0]:
            continue
        ika_num = str(row[4]).strip() if row[4] else ""
        name    = str(row[7]).strip() if row[7] else ""
        todoke  = str(row[13]).strip() if row[13] else ""

        if ika_num and name and ika_num not in ika_info:
            ika_info[ika_num] = {"name": name}

        flag_col = TODOKE_TO_FLAG.get(todoke)
        if flag_col and ika_num:
            ika_flags.setdefault(ika_num, set()).add(flag_col)

    wb.close()

    # 正規化名称 → フラグdict
    shisetsu: dict[str, dict] = {}
    for ika_num, info in ika_info.items():
        norm = normalize(info["name"])
        flags = ika_flags.get(ika_num, set())
        flag_dict = {f: 1 for f in flags}
        if norm in shisetsu:
            for k, v in flag_dict.items():
                shisetsu[norm][k] = max(shisetsu[norm].get(k, 0), v)
        else:
            shisetsu[norm] = flag_dict

    # 全フラグを0にリセット
    conn.execute(f"UPDATE pharmacies SET {', '.join(f+' = 0' for f in ALL_FLAGS)}")

    # マッチング・更新
    db_rows = conn.execute("SELECT id, name FROM pharmacies").fetchall()
    updates = []
    for pid, db_name in db_rows:
        norm_db = normalize(db_name)
        info = shisetsu.get(norm_db)
        if not info:
            for norm_s, d in shisetsu.items():
                if norm_db in norm_s or norm_s in norm_db:
                    info = d
                    break
        if info:
            row = tuple(info.get(f, 0) for f in ALL_FLAGS) + (pid,)
            updates.append(row)

    set_clause = ", ".join(f"{f}=?" for f in ALL_FLAGS)
    conn.executemany(f"UPDATE pharmacies SET {set_clause} WHERE id=?", updates)
    conn.commit()
    return len(ika_info), len(updates)


def run_shisetsu_update(versions: dict) -> dict:
    """施設基準届出の更新を試みる。更新結果を返す"""
    current_ver = versions["shisetsu"]["version"]
    print(f"\n[施設基準届出] 現在バージョン: {current_ver}")

    result = find_latest_shisetsu(current_ver)
    if not result:
        print("  最新版なし（更新不要）")
        return {"updated": False, "version": current_ver}

    new_ver, url, zip_data = result
    print(f"  新バージョン発見: {new_ver} ({url})")

    # ZIPから千葉県Excelを抽出
    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        # 千葉（12）のExcelを探す
        chiba_files = [n for n in z.namelist()
                       if n.startswith("12") and n.endswith(".xlsx")]
        if not chiba_files:
            # ファイル名に "千葉" または "chiba" を含むものを探す
            chiba_files = [n for n in z.namelist()
                           if ("千葉" in n or "chiba" in n.lower()) and n.endswith(".xlsx")]
        if not chiba_files:
            print(f"  [ERROR] ZIP内に千葉県Excelが見つかりません: {z.namelist()[:10]}")
            return {"updated": False, "version": current_ver, "error": "chiba excel not found"}

        excel_bytes = z.read(chiba_files[0])
        print(f"  Excel: {chiba_files[0]} ({len(excel_bytes):,} bytes)")

    # DBのサービスフラグを更新
    conn = sqlite3.connect(DB_PATH)
    ika_count, matched = update_service_flags(excel_bytes, conn)
    conn.close()
    print(f"  届出薬局: {ika_count}件 / マッチング更新: {matched}件")

    # バージョン記録を更新
    versions["shisetsu"] = {
        "version": new_ver,
        "date": datetime.date.today().isoformat(),
        "source": url,
        "note": f"令和{int(new_ver[1:3])}年{int(new_ver[3:5])}月 施設基準届出受理状況"
    }
    return {"updated": True, "version": new_ver, "ika_count": ika_count, "matched": matched}


# ── GMIS 新版チェック ─────────────────────────────────────────

def check_gmis_update(versions: dict) -> dict:
    """
    GMISの新版が出ていないか確認（6月/12月更新）
    新版あり → 通知のみ（フルパイプラインは手動）
    """
    current_ver = versions["gmis"]["version"]
    print(f"\n[GMIS薬局機能情報] 現在バージョン: {current_ver}")

    today = datetime.date.today()
    candidates = []
    # 直近の6月1日・12月1日を生成
    for year in [today.year, today.year - 1]:
        for month in [12, 6]:
            d = datetime.date(year, month, 1)
            ver = d.strftime("%Y%m%d")
            if ver > current_ver:
                candidates.append((ver, GMIS_BASE.format(date=ver)))

    for ver, url in candidates:
        print(f"  試行: {url}")
        r = try_download(url)
        if r:
            print(f"  新バージョン発見: {ver}")
            return {"updated": False, "new_version": ver, "url": url,
                    "note": "新版あり・手動インポートが必要"}

    print("  最新版なし（更新不要）")
    return {"updated": False, "version": current_ver}


# ── メイン ────────────────────────────────────────────────────

def main():
    print("=== データ自動更新チェック ===")
    print(f"実行日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

    versions = load_versions()
    results = {}

    # ① 施設基準届出
    results["shisetsu"] = run_shisetsu_update(versions)

    # ② GMIS
    results["gmis"] = check_gmis_update(versions)

    # バージョンファイル保存
    save_versions(versions)

    # サマリー表示
    print("\n=== 更新サマリー ===")
    shisetsu = results["shisetsu"]
    gmis = results["gmis"]

    if shisetsu.get("updated"):
        print(f"  施設基準届出: {shisetsu['version']} に更新完了")
    else:
        print(f"  施設基準届出: 更新なし ({versions['shisetsu']['version']})")

    if "new_version" in gmis:
        print(f"  GMIS: 新版あり ({gmis['new_version']}) → 手動インポートが必要")
    else:
        print(f"  GMIS: 更新なし ({versions['gmis']['version']})")

    # GitHub Actions 出力
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    shisetsu_updated = str(shisetsu.get("updated", False)).lower()
    gmis_new = "true" if "new_version" in gmis else "false"
    gmis_new_ver = gmis.get("new_version", "")

    if github_output:
        with open(github_output, "a") as f:
            f.write(f"shisetsu_updated={shisetsu_updated}\n")
            f.write(f"shisetsu_version={shisetsu.get('version', '')}\n")
            f.write(f"gmis_new={gmis_new}\n")
            f.write(f"gmis_new_version={gmis_new_ver}\n")
    else:
        print(f"\nGitHub出力: shisetsu_updated={shisetsu_updated}, gmis_new={gmis_new}")

    print("\n[完了]")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
全国ドラッグストア上位チェーン 店舗一覧スクレイプ
- 各チェーンの公式サイト/APIから店舗一覧を取得
- ds_chains/ にJSON保存 → 各県DBのpharmaciesテーブルに追加
"""

import requests
import json
import sqlite3
import math
import os
import re
import time
import sys
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote

# 出力バッファリングを無効化
sys.stdout.reconfigure(line_buffering=True)

HOME = Path.home()
BASE_DIR = HOME / "chiba_pdf_db"
CHAINS_DIR = BASE_DIR / "ds_chains"
CHAINS_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}
SLEEP_SEC = 3  # サイト間のsleep

# ── 都道府県名 → コード ──
PREF_NAMES = {
    1: "北海道", 2: "青森県", 3: "岩手県", 4: "宮城県", 5: "秋田県",
    6: "山形県", 7: "福島県", 8: "茨城県", 9: "栃木県", 10: "群馬県",
    11: "埼玉県", 12: "千葉県", 13: "東京都", 14: "神奈川県", 15: "新潟県",
    16: "富山県", 17: "石川県", 18: "福井県", 19: "山梨県", 20: "長野県",
    21: "岐阜県", 22: "静岡県", 23: "愛知県", 24: "三重県", 25: "滋賀県",
    26: "京都府", 27: "大阪府", 28: "兵庫県", 29: "奈良県", 30: "和歌山県",
    31: "鳥取県", 32: "島根県", 33: "岡山県", 34: "広島県", 35: "山口県",
    36: "徳島県", 37: "香川県", 38: "愛媛県", 39: "高知県", 40: "福岡県",
    41: "佐賀県", 42: "長崎県", 43: "熊本県", 44: "大分県", 45: "宮崎県",
    46: "鹿児島県", 47: "沖縄県",
}
PREF_NAME_TO_CODE = {v: k for k, v in PREF_NAMES.items()}
# 都/府/県なしバージョンも追加
for _pname, _pcode in list(PREF_NAME_TO_CODE.items()):
    for suffix in ["都", "府", "県"]:
        if _pname.endswith(suffix):
            PREF_NAME_TO_CODE[_pname[:-1]] = _pcode

PREF_CAPITALS = {
    1: (43.0642, 141.3469), 2: (40.8244, 140.7400), 3: (39.7036, 141.1527),
    4: (38.2689, 140.8720), 5: (39.7186, 140.1024), 6: (38.2405, 140.3633),
    7: (37.7503, 140.4676), 8: (36.3419, 140.4468), 9: (36.5657, 139.8836),
    10: (36.3911, 139.0608), 11: (35.8569, 139.6489), 12: (35.6047, 140.1233),
    13: (35.6895, 139.6917), 14: (35.4478, 139.6425), 15: (37.9026, 139.0236),
    16: (36.6953, 137.2114), 17: (36.5947, 136.6256), 18: (36.0652, 136.2219),
    19: (35.6642, 138.5683), 20: (36.2333, 138.1811), 21: (35.3912, 136.7222),
    22: (34.9769, 138.3831), 23: (35.1803, 136.9066), 24: (34.7303, 136.5086),
    25: (35.0045, 135.8686), 26: (35.0214, 135.7556), 27: (34.6864, 135.5200),
    28: (34.6913, 135.1830), 29: (34.6853, 135.8328), 30: (34.2261, 135.1675),
    31: (35.5036, 134.2383), 32: (35.4723, 133.0505), 33: (34.6617, 133.9350),
    34: (34.3963, 132.4596), 35: (34.1861, 131.4714), 36: (34.0658, 134.5594),
    37: (34.3401, 134.0434), 38: (33.8416, 132.7661), 39: (33.5597, 133.5311),
    40: (33.6064, 130.4183), 41: (33.2494, 130.2988), 42: (32.7448, 129.8737),
    43: (32.7898, 130.7417), 44: (33.2382, 131.6126), 45: (31.9111, 131.4239),
    46: (31.5602, 130.5581), 47: (26.2124, 127.6809),
}


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def assign_prefecture_by_coords(lat, lon):
    """緯度経度から最寄り都道府県コードを返す"""
    if lat is None or lon is None:
        return None
    if lat < 20 or lat > 46 or lon < 122 or lon > 154:
        return None
    best_code, best_dist = None, float("inf")
    for code, (clat, clon) in PREF_CAPITALS.items():
        d = haversine_m(lat, lon, clat, clon)
        if d < best_dist:
            best_dist = d
            best_code = code
    return best_code


def pref_name_to_code(name: str):
    """都道府県名からコードを返す"""
    if not name:
        return None
    # 完全一致
    if name in PREF_NAME_TO_CODE:
        return PREF_NAME_TO_CODE[name]
    # 部分一致
    for pname, code in PREF_NAME_TO_CODE.items():
        if pname in name or name in pname:
            return code
    return None


def get_db_path(code: int):
    if code == 12:
        return HOME / "chiba_pdf_db" / "chiba_iryo.db"
    elif code == 27:
        return HOME / "osaka_pdf_db" / "osaka_iryo.db"
    else:
        name = PREF_NAMES.get(code)
        if not name:
            return None
        dir_name = f"prefdb_{code:02d}_{name}"
        db_name = f"{code:02d}_iryo.db"
        path = HOME / dir_name / db_name
        if path.exists():
            return path
    return None


# ═══════════════════════════════════════════════════════════
# チェーン別スクレイパー
# ═══════════════════════════════════════════════════════════

def scrape_tsuruha():
    """ツルハグループ (shop.tsuruha-g.com Yext)"""
    chain_name = "ツルハグループ"
    print(f"\n{'='*60}")
    print(f"スクレイプ開始: {chain_name}")
    print(f"{'='*60}")

    base = "https://shop.tsuruha-g.com"
    stores = []

    # Step 1: 都道府県一覧を取得
    r = requests.get(f"{base}/shop", headers=HEADERS, timeout=30)
    html = unquote(r.text)
    prefs = re.findall(r'"name":"([^"]+)","slug":"([^"]+)"', html)
    print(f"  都道府県数: {len(prefs)}")

    brand_map = {
        "TSURUHA_DRUG": "ツルハドラッグ",
        "KUSURI_NO_FUKUTARO": "くすりの福太郎",
        "WELLNES": "ウォンツ",
        "B_AND_D": "B&Dドラッグストア",
        "LADY_DRUG": "レデイ薬局",
        "TSURUHA_DRUG_DISPENSING": "ツルハドラッグ調剤",
    }

    for pref_name, pref_slug in prefs:
        time.sleep(SLEEP_SEC)
        # 市区町村一覧を取得
        try:
            r = requests.get(f"{base}/{pref_slug}", headers=HEADERS, timeout=30)
            html = unquote(r.text)
            cities = re.findall(r'"name":"([^"]+)","slug":"([^"]+)"', html)
        except Exception as e:
            print(f"  ！{pref_name} 都道府県ページ取得エラー: {e}")
            continue

        pref_count = 0
        for city_name, city_slug in cities:
            time.sleep(1)  # 同一サイト内は1秒間隔
            try:
                r = requests.get(f"{base}/{city_slug}", headers=HEADERS, timeout=30)
                html = unquote(r.text)
                match = re.search(
                    r'"dm_directoryChildren"\s*:\s*(\[[\s\S]*?\])\s*,\s*"dm_directoryParents',
                    html,
                )
                if not match:
                    continue
                city_stores = json.loads(match.group(1))
            except Exception as e:
                print(f"    ！{city_name} 取得エラー: {e}")
                continue

            for s in city_stores:
                addr = s.get("address", {})
                coord = s.get("yextDisplayCoordinate", {})
                brand = s.get("c_brandFilter", "")
                dispensing = s.get("c_dispensingForm", "")

                address = f"{addr.get('region', '')}{addr.get('city', '')}{addr.get('sublocality', '')}{addr.get('line1', '')}".strip()
                pref_code = pref_name_to_code(addr.get("region", ""))

                stores.append({
                    "name": s.get("name", ""),
                    "address": address,
                    "lat": coord.get("latitude"),
                    "lon": coord.get("longitude"),
                    "pref_code": pref_code,
                    "pref_name": addr.get("region", pref_name),
                    "chain_name": chain_name,
                    "brand": brand_map.get(brand, brand),
                    "dispensing": dispensing,
                })
                pref_count += 1

        print(f"  {pref_name}: {pref_count}件 ({len(cities)}市区町村)")

    print(f"  合計: {len(stores)}件")
    return stores


def scrape_sugi():
    """スギ薬局 (bff.sugi-net.jp BFF API)"""
    chain_name = "スギ薬局"
    print(f"\n{'='*60}")
    print(f"スクレイプ開始: {chain_name}")
    print(f"{'='*60}")

    bff = "https://bff.sugi-net.jp"
    headers = {
        **HEADERS,
        "Origin": "https://www.sugi-net.jp",
        "Referer": "https://www.sugi-net.jp/",
    }

    stores = []

    # Step 1: エリア一覧取得
    r = requests.get(f"{bff}/store-areas", headers=headers, timeout=30)
    data = r.json()
    areas = data.get("areas", [])

    # 全都道府県コードを収集
    pref_ids = []
    for region in areas:
        for pref in region.get("children", []):
            pref_ids.append((pref["id"], pref["name"]))

    print(f"  対象都道府県: {len(pref_ids)}")

    for pref_id, pref_name in pref_ids:
        time.sleep(SLEEP_SEC)
        page = 1
        pref_count = 0
        while page <= 200:  # 安全上限
            try:
                r = requests.get(
                    f"{bff}/stores/by-area",
                    params={"storeArea": pref_id, "page": page},
                    headers=headers,
                    timeout=30,
                )
                data = r.json()
                page_stores = data.get("stores", [])
                total = data.get("totalNum", 0)
            except Exception as e:
                print(f"  ！{pref_name} page {page} エラー: {e}")
                break

            if not page_stores:
                break

            for s in page_stores:
                addr_raw = s.get("address", "")
                # 〒XXX-XXXX を除去
                addr_clean = re.sub(r"〒\d{3}-\d{4}\s*", "", addr_raw).strip()
                # 都道府県コードを推定
                pref_code = int(pref_id[:2]) if len(pref_id) >= 2 else None
                pos = s.get("position", {})

                stores.append({
                    "name": s.get("name", ""),
                    "address": addr_clean,
                    "lat": pos.get("lat"),
                    "lon": pos.get("lng"),
                    "pref_code": pref_code,
                    "pref_name": pref_name,
                    "chain_name": chain_name,
                    "brand": "スギ薬局",
                    "dispensing": "",  # storeInfoに情報あるが省略
                })
                pref_count += 1

            if pref_count >= total or len(page_stores) < 10:
                break
            page += 1
            time.sleep(1)  # ページング間は短め

        print(f"  {pref_name}: {pref_count}件")

    print(f"  合計: {len(stores)}件")
    return stores


def scrape_aoki():
    """クスリのアオキ (kusuri-aoki-shop-info.com API)"""
    chain_name = "クスリのアオキ"
    print(f"\n{'='*60}")
    print(f"スクレイプ開始: {chain_name}")
    print(f"{'='*60}")

    base = "https://kusuri-aoki-shop-info.com"
    stores = []

    # Step 1: 都道府県(city)一覧を取得
    r = requests.get(f"{base}/api/v1/app/address/city/listCities", headers=HEADERS, timeout=30)
    data = r.json()
    cities = data.get("data", [])
    print(f"  対象都道府県: {len(cities)}")

    for city in cities:
        city_id = city["id"]
        city_name = city["name"]
        city_code = city.get("code", "")
        pref_code = int(city_code) if city_code.isdigit() else pref_name_to_code(city_name)
        time.sleep(SLEEP_SEC)

        page = 1
        city_count = 0
        while True:
            try:
                r = requests.get(
                    f"{base}/result",
                    params={"cityId": city_id, "page": page, "size": 100},
                    headers=HEADERS,
                    timeout=30,
                )
                html = r.text
                # pageStores変数からデータ抽出
                match = re.search(r"var\s+pageStores\s*=\s*({.*?});\s*\n", html, re.DOTALL)
                if not match:
                    break
                page_data = json.loads(match.group(1))
                content = page_data.get("content", [])
                total_pages = page_data.get("totalPages", 1)
            except Exception as e:
                print(f"  ！{city_name} page {page} エラー: {e}")
                break

            if not content:
                break

            for s in content:
                stores.append({
                    "name": f"クスリのアオキ {s.get('name', '')}",
                    "address": s.get("address", ""),
                    "lat": s.get("latitude"),
                    "lon": s.get("longitude"),
                    "pref_code": pref_code,
                    "pref_name": city_name,
                    "chain_name": chain_name,
                    "brand": "クスリのアオキ",
                    "dispensing": "",
                })
                city_count += 1

            if page >= total_pages:
                break
            page += 1
            time.sleep(1)

        print(f"  {city_name}: {city_count}件")

    print(f"  合計: {len(stores)}件")
    return stores


# ═══════════════════════════════════════════════════════════
# DB追加ロジック
# ═══════════════════════════════════════════════════════════

def ensure_columns(conn):
    """必要なカラムがなければ追加"""
    cols = [row[1] for row in conn.execute("PRAGMA table_info(pharmacies)").fetchall()]
    if "ds_only" not in cols:
        conn.execute("ALTER TABLE pharmacies ADD COLUMN ds_only INTEGER DEFAULT 0")
    if "chain_name" not in cols:
        conn.execute("ALTER TABLE pharmacies ADD COLUMN chain_name TEXT")
    conn.commit()


def get_existing(conn):
    """既存薬局の(name, lat, lon)リストを返す"""
    return conn.execute("SELECT name, lat, lon FROM pharmacies").fetchall()


def is_duplicate(store, existing_list):
    """重複判定: 座標100m以内"""
    slat, slon = store.get("lat"), store.get("lon")
    sname = store.get("name", "")
    for ename, elat, elon in existing_list:
        # 名前完全一致
        if ename and sname and ename == sname:
            return True
        # 座標100m以内
        if elat and elon and slat and slon:
            if haversine_m(slat, slon, elat, elon) < 100:
                return True
    return False


def add_stores_to_dbs(all_stores: list):
    """全店舗をDBに追加"""
    print(f"\n{'='*60}")
    print("DBへの追加処理")
    print(f"{'='*60}")

    # 都道府県別に分類
    by_pref = {}
    no_pref = 0
    for s in all_stores:
        code = s.get("pref_code")
        if code is None and s.get("lat") and s.get("lon"):
            code = assign_prefecture_by_coords(s["lat"], s["lon"])
            s["pref_code"] = code
        if code is None:
            no_pref += 1
            continue
        by_pref.setdefault(code, []).append(s)

    if no_pref:
        print(f"  都道府県不明: {no_pref}件スキップ")

    results = {}
    total_added = 0
    total_dup = 0
    today = datetime.now().strftime("%Y-%m-%d")

    for code in sorted(by_pref.keys()):
        stores = by_pref[code]
        pref_name = PREF_NAMES.get(code, f"?{code}")
        db_path = get_db_path(code)

        if db_path is None or not db_path.exists():
            results[code] = {"name": pref_name, "added": 0, "dup": 0, "no_db": len(stores)}
            continue

        # バックアップ
        bak = db_path.with_suffix(f".db.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        os.system(f'cp "{db_path}" "{bak}"')

        conn = sqlite3.connect(str(db_path))
        ensure_columns(conn)
        existing = get_existing(conn)

        added = 0
        dup = 0
        for s in stores:
            if is_duplicate(s, existing):
                dup += 1
                continue
            conn.execute(
                """INSERT INTO pharmacies (name, address, lat, lon, ds_only, chain_name, data_date)
                   VALUES (?, ?, ?, ?, 1, ?, ?)""",
                (s["name"], s.get("address"), s.get("lat"), s.get("lon"),
                 s["chain_name"], today),
            )
            existing.append((s["name"], s.get("lat"), s.get("lon")))
            added += 1

        conn.commit()
        conn.close()

        total_added += added
        total_dup += dup
        results[code] = {"name": pref_name, "added": added, "dup": dup, "no_db": 0}
        if added > 0:
            print(f"  {code:02d} {pref_name}: +{added}件 (重複: {dup}件)")

    return results, total_added, total_dup


# ═══════════════════════════════════════════════════════════
# メイン
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("全国ドラッグストア上位チェーン スクレイプ")
    print(f"実行日時: {datetime.now().isoformat()}")
    print("=" * 60)

    chain_scrapers = [
        ("tsuruha", "ツルハグループ", scrape_tsuruha),
        ("sugi", "スギ薬局", scrape_sugi),
        ("aoki", "クスリのアオキ", scrape_aoki),
    ]

    all_stores = []
    chain_results = {}

    for key, name, scraper in chain_scrapers:
        cache_file = CHAINS_DIR / f"{key}.json"

        # キャッシュがあればスキップ
        if cache_file.exists():
            print(f"\n  キャッシュ使用: {cache_file}")
            with open(cache_file, encoding="utf-8") as f:
                stores = json.load(f)
            print(f"  {name}: {len(stores)}件（キャッシュ）")
        else:
            try:
                stores = scraper()
            except Exception as e:
                print(f"  ！{name} スクレイプ失敗: {e}")
                stores = []

            # JSON保存
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(stores, f, ensure_ascii=False, indent=2)
            print(f"  保存: {cache_file}")

        chain_results[name] = len(stores)
        all_stores.extend(stores)

    print(f"\n全チェーン合計: {len(all_stores)}件")

    # DB追加
    results, total_added, total_dup = add_stores_to_dbs(all_stores)

    # ═══ 結果レポート ═══
    print("\n" + "=" * 60)
    print("結果サマリー")
    print("=" * 60)

    print("\n■ チェーン別取得件数:")
    for name, count in chain_results.items():
        print(f"  {name}: {count}件")
    print(f"  合計: {len(all_stores)}件")

    print(f"\n■ DB追加: {total_added}件 / 重複除外: {total_dup}件")

    print("\n■ 都道府県別追加件数（上位10）:")
    sorted_results = sorted(results.items(), key=lambda x: x[1]["added"], reverse=True)
    for code, r in sorted_results[:10]:
        if r["added"] > 0:
            print(f"  {code:02d} {r['name']}: +{r['added']}件 (重複: {r['dup']}件)")

    # DS専用店舗の総数を各DBから集計
    print("\n■ 各県DS専用店舗 総数:")
    ds_total = 0
    for code in range(1, 48):
        db_path = get_db_path(code)
        if db_path and db_path.exists():
            conn = sqlite3.connect(str(db_path))
            try:
                cnt = conn.execute("SELECT COUNT(*) FROM pharmacies WHERE ds_only=1").fetchone()[0]
                ds_total += cnt
                if cnt > 0:
                    pass  # 大量出力を避ける
            except Exception:
                pass
            conn.close()
    print(f"  全国DS専用店舗 合計: {ds_total}件")

    # 結果ファイル保存
    report_dir = HOME / "Library/Mobile Documents/com~apple~CloudDocs/Documents/Obsidian_Integlation/inbox/claude_results"
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"ds_chains_{ts}.txt"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("全国ドラッグストア上位チェーン スクレイプ結果\n")
        f.write(f"実行日時: {datetime.now().isoformat()}\n\n")
        f.write("■ チェーン別取得件数:\n")
        for name, count in chain_results.items():
            f.write(f"  {name}: {count}件\n")
        f.write(f"  合計: {len(all_stores)}件\n\n")
        f.write(f"■ DB追加: {total_added}件 / 重複除外: {total_dup}件\n\n")
        f.write("■ 都道府県別:\n")
        f.write(f"{'コード':>4} {'都道府県':<8} {'追加':>5} {'重複':>5}\n")
        f.write("-" * 35 + "\n")
        for code in sorted(results.keys()):
            r = results[code]
            f.write(f"  {code:02d}  {r['name']:<8} {r['added']:>5} {r['dup']:>5}\n")
        f.write(f"\n全国DS専用店舗 合計: {ds_total}件\n")

    print(f"\n結果ファイル: {report_path}")
    print("完了！")


if __name__ == "__main__":
    main()

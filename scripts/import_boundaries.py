"""
市区町村境界 & 二次医療圏境界を SQLite にインポートするスクリプト

処理フロー:
  1. N03 GeoJSONから市区町村ポリゴンを読み込み・dissolve
  2. 薬局DBのiryo_ken列で市区町村→医療圏をマッピング
  3. 医療圏ごとにポリゴンをunary_unionして二次医療圏を生成
  4. city_boundaries / iryo_ken_boundaries テーブルに書き出し

実行例:
  python scripts/import_boundaries.py \
    --zip "path/to/N03-20230101_12_GML.zip"
"""

import argparse
import json
import sqlite3
import zipfile
from pathlib import Path
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

ROOT    = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "chiba_iryo.db"


def load_geojson(zip_path: str) -> list:
    with zipfile.ZipFile(zip_path) as z:
        name = [n for n in z.namelist() if n.endswith(".geojson")][0]
        raw = z.read(name)
    data = json.loads(raw.decode("utf-8"))
    return data["features"]


def dissolve_by_city(features: list) -> dict:
    """N03_007（市区町村コード）ごとにポリゴンをdissolve"""
    city_map: dict[str, dict] = {}
    for feat in features:
        props = feat["properties"]
        code = props.get("N03_007", "")
        name = props.get("N03_004", "") or props.get("N03_003", "")
        if not code:
            continue
        geom = shape(feat["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        if code not in city_map:
            city_map[code] = {"name": name, "geoms": []}
        city_map[code]["geoms"].append(geom)

    result = {}
    for code, d in city_map.items():
        merged = unary_union(d["geoms"])
        centroid = merged.centroid
        result[code] = {
            "city_code": code,
            "city_name": d["name"],
            "centroid_lat": round(centroid.y, 6),
            "centroid_lon": round(centroid.x, 6),
            "geometry_json": json.dumps(mapping(merged), ensure_ascii=False),
        }
    return result


def get_city_to_iryo_ken(conn: sqlite3.Connection) -> dict:
    """薬局DBからcity_code→iryo_kenのマッピングを取得
    薬局のcity_codeは3桁整数（N03_007の5桁コード - 12000）"""
    rows = conn.execute("""
        SELECT city_code, iryo_ken, COUNT(*) as cnt
        FROM pharmacies
        WHERE city_code IS NOT NULL AND iryo_ken IS NOT NULL
        GROUP BY city_code, iryo_ken
        ORDER BY city_code, cnt DESC
    """).fetchall()
    # 各city_codeで最多のiryo_kenを採用
    # 薬局DB: 217 → N03: "12217"
    mapping_dict = {}
    for city_code, iryo_ken, cnt in rows:
        n03_code = str(12000 + int(city_code))  # 217 → "12217"
        if n03_code not in mapping_dict:
            mapping_dict[n03_code] = iryo_ken
    # 千葉市の区（12101〜12106）は「千葉」圏域に割り当て
    for ward_code in ["12101","12102","12103","12104","12105","12106"]:
        if ward_code not in mapping_dict:
            mapping_dict[ward_code] = "千葉"
    return mapping_dict


def build_iryo_ken_boundaries(city_data: dict, city_to_ken: dict) -> dict:
    """市区町村ポリゴンを医療圏ごとにunary_union"""
    ken_map: dict[str, list] = {}
    for code, d in city_data.items():
        iryo_ken = city_to_ken.get(code)
        if not iryo_ken:
            continue
        geom = shape(json.loads(d["geometry_json"]))
        if iryo_ken not in ken_map:
            ken_map[iryo_ken] = []
        ken_map[iryo_ken].append(geom)

    result = {}
    for ken, geoms in ken_map.items():
        merged = unary_union(geoms)
        centroid = merged.centroid
        result[ken] = {
            "iryo_ken": ken,
            "centroid_lat": round(centroid.y, 6),
            "centroid_lon": round(centroid.x, 6),
            "geometry_json": json.dumps(mapping(merged), ensure_ascii=False),
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True, help="N03 GML ZIPパス")
    args = parser.parse_args()

    print("[START] 市区町村・二次医療圏境界インポート")

    features = load_geojson(args.zip)
    print(f"  元ポリゴン数: {len(features):,}")

    print("  市区町村dissolve中...")
    city_data = dissolve_by_city(features)
    print(f"  市区町村数: {len(city_data)}")

    conn = sqlite3.connect(DB_PATH)
    city_to_ken = get_city_to_iryo_ken(conn)
    print(f"  iryo_kenマッピング: {len(city_to_ken)}市区町村")

    print("  二次医療圏dissolve中...")
    iryo_ken_data = build_iryo_ken_boundaries(city_data, city_to_ken)
    print(f"  二次医療圏数: {len(iryo_ken_data)}")

    # ── city_boundaries テーブル ──────────────────────────
    conn.execute("DROP TABLE IF EXISTS city_boundaries")
    conn.execute("""
        CREATE TABLE city_boundaries (
            city_code    TEXT PRIMARY KEY,
            city_name    TEXT,
            iryo_ken     TEXT,
            centroid_lat REAL,
            centroid_lon REAL,
            geometry_json TEXT
        )
    """)
    for code, d in city_data.items():
        conn.execute("""
            INSERT INTO city_boundaries VALUES (?,?,?,?,?,?)
        """, (
            code, d["city_name"],
            city_to_ken.get(code),
            d["centroid_lat"], d["centroid_lon"],
            d["geometry_json"],
        ))

    # ── iryo_ken_boundaries テーブル ─────────────────────
    conn.execute("DROP TABLE IF EXISTS iryo_ken_boundaries")
    conn.execute("""
        CREATE TABLE iryo_ken_boundaries (
            iryo_ken     TEXT PRIMARY KEY,
            centroid_lat REAL,
            centroid_lon REAL,
            geometry_json TEXT
        )
    """)
    for ken, d in iryo_ken_data.items():
        conn.execute("""
            INSERT INTO iryo_ken_boundaries VALUES (?,?,?,?)
        """, (ken, d["centroid_lat"], d["centroid_lon"], d["geometry_json"]))

    conn.commit()

    c1 = conn.execute("SELECT COUNT(*) FROM city_boundaries").fetchone()[0]
    c2 = conn.execute("SELECT COUNT(*) FROM iryo_ken_boundaries").fetchone()[0]
    kens = [r[0] for r in conn.execute("SELECT iryo_ken FROM iryo_ken_boundaries").fetchall()]
    conn.close()

    print(f"[OK] city_boundaries: {c1}件")
    print(f"[OK] iryo_ken_boundaries: {c2}件 → {kens}")


if __name__ == "__main__":
    main()

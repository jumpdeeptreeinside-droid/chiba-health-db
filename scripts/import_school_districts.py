"""
国土数値情報 中学校区ポリゴンを SQLite にインポートするスクリプト

出力テーブル: school_districts（chiba_iryo.db）
  - district_id  : A32_003（学校コード）
  - city_name    : A32_002（市区町村名）
  - school_name  : A32_004（学校名）
  - address      : A32_005（住所）
  - geometry_json: GeoJSON文字列（ポリゴン）
  - centroid_lat / centroid_lon: 重心座標

実行例:
  python scripts/import_school_districts.py \
    --zip "path/to/A32-21_12_GML.zip"
"""

import argparse
import json
import sqlite3
import zipfile
from pathlib import Path


ROOT    = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "chiba_iryo.db"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True, help="A32-21_12_GML.zip のパス")
    args = parser.parse_args()

    print("[START] 中学校区データ インポート")

    # GeoJSONを直接読み込み（UTF-8 / cp932 両対応）
    with zipfile.ZipFile(args.zip) as z:
        geojson_name = [n for n in z.namelist() if n.endswith(".geojson")][0]
        raw = z.read(geojson_name)
        for enc in ("utf-8", "utf-8-sig", "cp932"):
            try:
                data = json.loads(raw.decode(enc))
                break
            except Exception:
                continue

    features = data["features"]
    print(f"  中学校区数: {len(features)} 件")

    # 重心計算（簡易版：座標の平均）
    def centroid(geom):
        coords = []
        def collect(c):
            if isinstance(c[0], list):
                for x in c: collect(x)
            else:
                coords.append(c)
        collect(geom["coordinates"])
        if not coords:
            return None, None
        lats = [c[1] for c in coords]
        lons = [c[0] for c in coords]
        return round(sum(lats)/len(lats), 6), round(sum(lons)/len(lons), 6)

    records = []
    for feat in features:
        props = feat.get("properties", {})
        lat, lon = centroid(feat["geometry"])
        records.append({
            "district_id":   props.get("A32_003", ""),
            "city_code":     props.get("A32_001", ""),
            "city_name":     props.get("A32_002", ""),
            "school_name":   props.get("A32_004", ""),
            "address":       props.get("A32_005", ""),
            "centroid_lat":  lat,
            "centroid_lon":  lon,
            "geometry_json": json.dumps(feat["geometry"], ensure_ascii=False),
        })

    conn = sqlite3.connect(DB_PATH)
    conn.execute("DROP TABLE IF EXISTS school_districts")
    conn.execute("""
        CREATE TABLE school_districts (
            district_id   TEXT PRIMARY KEY,
            city_code     TEXT,
            city_name     TEXT,
            school_name   TEXT,
            address       TEXT,
            centroid_lat  REAL,
            centroid_lon  REAL,
            geometry_json TEXT
        )
    """)
    conn.executemany("""
        INSERT OR REPLACE INTO school_districts VALUES
        (:district_id, :city_code, :city_name, :school_name,
         :address, :centroid_lat, :centroid_lon, :geometry_json)
    """, records)
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM school_districts").fetchone()[0]
    sample = conn.execute(
        "SELECT city_name, school_name, centroid_lat, centroid_lon "
        "FROM school_districts LIMIT 3"
    ).fetchall()
    conn.close()

    print(f"[OK] school_districts テーブル: {count} 件インポート完了")
    for row in sample:
        print(f"  {row[0]} / {row[1]} ({row[2]}, {row[3]})")


if __name__ == "__main__":
    main()

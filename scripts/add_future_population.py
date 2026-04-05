#!/usr/bin/env python3
"""
population_mesh テーブルに将来推計人口と高齢者人口を追加するスクリプト
データソース: 国土数値情報 500mメッシュ別将来推計人口データ（既にDL済みGeoJSON）
"""

import json
import sqlite3
import sys
from pathlib import Path


def update_db(db_path, geojson_path):
    print(f"\n=== {db_path.name} ===")
    print(f"  GeoJSON: {geojson_path}")

    with open(geojson_path, encoding="utf-8") as f:
        data = json.load(f)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # カラム追加（存在しなければ）
    new_cols = [
        ("pop_2025", "INTEGER"),
        ("pop_2030", "INTEGER"),
        ("pop_2035", "INTEGER"),
        ("pop_2040", "INTEGER"),
        ("pop_2050", "INTEGER"),
        ("elderly_65_2025", "INTEGER"),
        ("elderly_75_2025", "INTEGER"),
        ("elderly_65_2050", "INTEGER"),
        ("elderly_75_2050", "INTEGER"),
    ]

    existing = {row[1] for row in cur.execute("PRAGMA table_info(population_mesh)")}
    for col, typ in new_cols:
        if col not in existing:
            cur.execute(f"ALTER TABLE population_mesh ADD COLUMN {col} {typ}")
            print(f"  カラム追加: {col}")

    conn.commit()

    # GeoJSONからデータ抽出してUPDATE
    updated = 0
    for feat in data["features"]:
        p = feat["properties"]
        mesh_id = str(p.get("MESH_ID", ""))
        if not mesh_id:
            continue

        vals = {
            "pop_2025": round(p.get("PTN_2025") or 0),
            "pop_2030": round(p.get("PTN_2030") or 0),
            "pop_2035": round(p.get("PTN_2035") or 0),
            "pop_2040": round(p.get("PTN_2040") or 0),
            "pop_2050": round(p.get("PTN_2050") or 0),
            "elderly_65_2025": round(p.get("PTA_2025") or 0),
            "elderly_75_2025": round(p.get("PTE_2025") or 0),
            "elderly_65_2050": round(p.get("PTA_2050") or 0),
            "elderly_75_2050": round(p.get("PTE_2050") or 0),
        }

        cur.execute("""
            UPDATE population_mesh SET
                pop_2025=?, pop_2030=?, pop_2035=?, pop_2040=?, pop_2050=?,
                elderly_65_2025=?, elderly_75_2025=?,
                elderly_65_2050=?, elderly_75_2050=?
            WHERE mesh_code=?
        """, (*vals.values(), mesh_id))

        if cur.rowcount > 0:
            updated += 1

    conn.commit()

    # サマリー
    cur.execute("""
        SELECT medical_area,
               SUM(population) as pop_2020,
               SUM(pop_2030) as pop_2030,
               SUM(pop_2050) as pop_2050,
               SUM(elderly_75_2025) as e75_2025,
               SUM(elderly_75_2050) as e75_2050
        FROM population_mesh
        WHERE medical_area IS NOT NULL
        GROUP BY medical_area
        ORDER BY SUM(population) DESC
    """)

    print(f"\n  更新: {updated}メッシュ")
    print(f"\n  {'医療圏':<12} {'2020人口':>10} {'2030人口':>10} {'2050人口':>10} {'75+2025':>8} {'75+2050':>8} {'増減率':>6}")
    print(f"  {'-'*70}")
    for row in cur.fetchall():
        area, p20, p30, p50, e25, e50 = row
        change = ((p50 - p20) / p20 * 100) if p20 else 0
        print(f"  {area:<12} {p20:>10,} {p30:>10,} {p50:>10,} {e25:>8,} {e50:>8,} {change:>+5.1f}%")

    cur.execute("SELECT SUM(population), SUM(pop_2050), SUM(elderly_75_2050) FROM population_mesh")
    t20, t50, e50 = cur.fetchone()
    change_total = ((t50 - t20) / t20 * 100) if t20 else 0
    print(f"  {'合計':<12} {t20:>10,} {'':>10} {t50:>10,} {'':>8} {e50:>8,} {change_total:>+5.1f}%")

    conn.close()


if __name__ == "__main__":
    # 千葉
    chiba_db = Path.home() / "chiba_pdf_db" / "chiba_iryo.db"
    chiba_geojson = Path("/tmp/chiba_mesh500/500m_mesh_2024_12_GEOJSON/500m_mesh_2024_12.geojson")

    # 大阪
    osaka_db = Path.home() / "osaka_pdf_db" / "osaka_iryo.db"
    osaka_geojson = Path("/tmp/osaka_mesh500/500m_mesh_2024_27_GEOJSON/500m_mesh_2024_27.geojson")

    if chiba_geojson.exists() and chiba_db.exists():
        update_db(chiba_db, chiba_geojson)
    else:
        print(f"千葉: GeoJSON or DB not found")

    if osaka_geojson.exists() and osaka_db.exists():
        update_db(osaka_db, osaka_geojson)
    else:
        print(f"大阪: GeoJSON not found, downloading...")
        import subprocess
        Path("/tmp/osaka_mesh500").mkdir(exist_ok=True)
        subprocess.run([
            "curl", "-sL",
            "https://nlftp.mlit.go.jp/ksj/gml/data/m500r6/m500r6-24/500m_mesh_2024_27_GEOJSON.zip",
            "-o", "/tmp/osaka_mesh500.zip"
        ])
        subprocess.run(["unzip", "-o", "/tmp/osaka_mesh500.zip", "-d", "/tmp/osaka_mesh500"])
        # Re-check
        candidates = list(Path("/tmp/osaka_mesh500").rglob("*.geojson"))
        if candidates:
            update_db(osaka_db, candidates[0])
        else:
            print("  ERROR: GeoJSON not found after download")

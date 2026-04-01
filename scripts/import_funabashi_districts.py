"""
船橋市中学校区をVoronoi近似でDBに追加するスクリプト

処理フロー:
  1. 船橋市の26中学校をNominatimでジオコーディング
  2. 船橋市境界をメッシュデータのbboxから取得
  3. Voronoi分割 → 校区ポリゴン近似
  4. school_districtsテーブルに追記（city_code=12204）

注意: Voronoi近似のため実際の校区境界とは異なる場合があります
"""

import json
import sqlite3
import time
from pathlib import Path

from geopy.geocoders import Nominatim
from scipy.spatial import Voronoi
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, Point, box
from shapely.ops import unary_union

ROOT    = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "chiba_iryo.db"

SCHOOLS = [
    "船橋中学校", "湊中学校", "宮本中学校", "若松中学校", "海神中学校",
    "葛飾中学校", "行田中学校", "法田中学校", "旭中学校", "御滝中学校",
    "高根中学校", "八木が谷中学校", "前原中学校", "二宮中学校", "飯山満中学校",
    "芝山中学校", "七林中学校", "三田中学校", "三山中学校", "高根台中学校",
    "習志野台中学校", "古和釜中学校", "坪井中学校", "大穴中学校", "豊富中学校",
    "小室中学校",
]

# Nominatimで誤ヒットする学校の正確な座標（手動補正）
MANUAL_COORDS = {
    "法田中学校": (35.744444, 139.984500),
    "二宮中学校": (35.703920, 140.034940),
    "豊富中学校": (35.762450, 140.061910),
    "三田中学校": (35.698731, 140.044842),
}

# 船橋市のbounding box
FUNABASHI_BBOX = (139.95, 35.63, 140.08, 35.80)


def geocode_schools():
    """Nominatimで各学校の座標を取得"""
    geolocator = Nominatim(user_agent="chiba-health-db")
    results = []
    minx, miny, maxx, maxy = FUNABASHI_BBOX
    for name in SCHOOLS:
        # 手動補正座標が登録されていればそちらを優先
        if name in MANUAL_COORDS:
            lat, lon = MANUAL_COORDS[name]
            results.append({"name": name, "lat": lat, "lon": lon})
            print(f"  MN {name}: ({lat:.4f}, {lon:.4f})")
            continue
        query = f"千葉県船橋市 {name}"
        try:
            loc = geolocator.geocode(query, timeout=10)
            if loc and (miny <= loc.latitude <= maxy) and (minx <= loc.longitude <= maxx):
                results.append({"name": name, "lat": loc.latitude, "lon": loc.longitude})
                print(f"  OK {name}: ({loc.latitude:.4f}, {loc.longitude:.4f})")
            elif loc:
                # bbox外 = 誤ヒット
                print(f"  NG {name}: 誤ヒット ({loc.latitude:.4f}, {loc.longitude:.4f})")
            else:
                print(f"  NG {name}: 見つからず")
        except Exception as e:
            print(f"  NG {name}: エラー {e}")
        time.sleep(1.1)
    return results


def voronoi_polygons(schools, boundary_box):
    """Voronoi分割でポリゴンを生成しboundary_boxでクリップ"""
    points = np.array([[s["lon"], s["lat"]] for s in schools])

    # 境界外にダミー点を追加してVoronoiが無限になるのを防ぐ
    minx, miny, maxx, maxy = boundary_box.bounds
    margin = 0.05
    dummy = np.array([
        [minx - margin, miny - margin],
        [maxx + margin, miny - margin],
        [minx - margin, maxy + margin],
        [maxx + margin, maxy + margin],
        [(minx+maxx)/2, miny - margin],
        [(minx+maxx)/2, maxy + margin],
        [minx - margin, (miny+maxy)/2],
        [maxx + margin, (miny+maxy)/2],
    ])
    all_points = np.vstack([points, dummy])
    vor = Voronoi(all_points)

    polygons = []
    for i, school in enumerate(schools):
        region_idx = vor.point_region[i]
        region = vor.regions[region_idx]
        if -1 in region or not region:
            # 無限領域はboundary_boxで代替
            poly = boundary_box
        else:
            verts = [vor.vertices[v] for v in region]
            poly = Polygon(verts)
        clipped = poly.intersection(boundary_box)
        polygons.append(clipped)

    return polygons


def main():
    print("[START] 船橋市中学校区Voronoi近似インポート")

    # ジオコーディング
    print("\n学校位置をジオコーディング中...")
    schools = geocode_schools()
    if len(schools) < 5:
        print("[ERROR] ジオコーディング成功数が少なすぎます")
        return
    print(f"\n{len(schools)}/{len(SCHOOLS)}校 取得成功")

    # 船橋市の境界ボックス
    funabashi_bbox = box(*FUNABASHI_BBOX)

    # Voronoi分割
    print("\nVoronoi分割中...")
    polygons = voronoi_polygons(schools, funabashi_bbox)

    # DBに挿入
    conn = sqlite3.connect(DB_PATH)
    inserted = 0
    for school, poly in zip(schools, polygons):
        if poly is None or poly.is_empty:
            continue
        centroid = poly.centroid
        geom = poly.__geo_interface__
        conn.execute("""
            INSERT OR REPLACE INTO school_districts
            (district_id, city_code, city_name, school_name, address, centroid_lat, centroid_lon, geometry_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"12204_{school['name']}",
            "12204",
            "船橋市",
            school["name"],
            "（Voronoi近似）",
            round(centroid.y, 6),
            round(centroid.x, 6),
            json.dumps(geom, ensure_ascii=False),
        ))
        inserted += 1

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM school_districts WHERE city_code='12204'").fetchone()[0]
    conn.close()

    print(f"[OK] 船橋市 {inserted}校区をインポート完了（合計{total}件）")
    print("※ Voronoi近似のため実際の校区境界と異なる場合があります")


if __name__ == "__main__":
    main()

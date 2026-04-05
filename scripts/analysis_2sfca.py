#!/usr/bin/env python3
"""
2SFCA（Two-Step Floating Catchment Area）分析 MVP
薬局・医療機関のアクセシビリティを500mメッシュ単位で算出する

方式: 直線距離ベースの簡易2SFCA（Enhanced 2SFCA with distance decay）
- Step 1: 各供給点（薬局/医療機関）の供給能力 = 1 / 到達圏内人口
- Step 2: 各需要点（メッシュ）のアクセシビリティ = Σ(到達圏内供給点の供給能力)

距離減衰: ガウシアン関数 w(d) = exp(-d^2 / β^2)
閾値距離: 薬局=2km, 病院=5km（直線距離）
"""

import math
import sqlite3
import sys
import json
from pathlib import Path


def haversine_km(lat1, lon1, lat2, lon2):
    """2点間の直線距離（km）"""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def gaussian_weight(distance, threshold):
    """ガウシアン距離減衰"""
    if distance > threshold:
        return 0
    beta = threshold / 2
    return math.exp(-(distance**2) / (beta**2))


def run_2sfca(db_path, supply_table, threshold_km, label):
    """2SFCA分析を実行"""
    print(f"\n{'='*60}")
    print(f"2SFCA分析: {label} (閾値={threshold_km}km)")
    print(f"DB: {db_path.name}")
    print(f"{'='*60}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 需要点（人口メッシュ）
    cur.execute("""
        SELECT mesh_code, lat, lon, population, medical_area
        FROM population_mesh
        WHERE population > 0 AND lat IS NOT NULL
    """)
    meshes = cur.fetchall()
    print(f"  需要点（人口メッシュ）: {len(meshes)}")

    # 供給点
    if supply_table == "pharmacies":
        cur.execute("""
            SELECT id, lat, lon, iryo_ken FROM pharmacies
            WHERE lat IS NOT NULL AND lon IS NOT NULL
        """)
    else:
        cur.execute("""
            SELECT id, lat, lon, medical_area FROM medical_facilities
            WHERE lat IS NOT NULL AND lon IS NOT NULL
        """)
    supplies = cur.fetchall()
    print(f"  供給点（{supply_table}）: {len(supplies)}")

    if not supplies:
        print(f"  WARNING: 供給点にlat/lonがありません。スキップ。")
        conn.close()
        return None

    # Step 1: 各供給点の供給能力 R_j = 1 / Σ(w * P_k)
    print("  Step 1: 供給能力計算中...")
    supply_ratios = {}
    for s_id, s_lat, s_lon, s_area in supplies:
        if s_lat is None or s_lon is None:
            continue
        weighted_pop = 0
        for m_code, m_lat, m_lon, m_pop, m_area in meshes:
            dist = haversine_km(s_lat, s_lon, m_lat, m_lon)
            w = gaussian_weight(dist, threshold_km)
            if w > 0:
                weighted_pop += w * m_pop
        if weighted_pop > 0:
            supply_ratios[s_id] = 1.0 / weighted_pop
        else:
            supply_ratios[s_id] = 0

    # Step 2: 各メッシュのアクセシビリティ A_i = Σ(w * R_j)
    print("  Step 2: アクセシビリティ計算中...")
    accessibility = {}
    for m_code, m_lat, m_lon, m_pop, m_area in meshes:
        a_score = 0
        for s_id, s_lat, s_lon, s_area in supplies:
            if s_lat is None or s_lon is None:
                continue
            if s_id not in supply_ratios:
                continue
            dist = haversine_km(m_lat, m_lon, s_lat, s_lon)
            w = gaussian_weight(dist, threshold_km)
            if w > 0:
                a_score += w * supply_ratios[s_id]
        accessibility[m_code] = (a_score, m_area, m_pop)

    # 結果をDBに保存
    col_name = f"access_{supply_table[:4]}"  # access_phar or access_medi
    try:
        cur.execute(f"ALTER TABLE population_mesh ADD COLUMN {col_name} REAL")
    except:
        pass  # already exists

    for m_code, (score, _, _) in accessibility.items():
        cur.execute(f"UPDATE population_mesh SET {col_name}=? WHERE mesh_code=?",
                    (score, m_code))
    conn.commit()

    # 医療圏別サマリー
    area_stats = {}
    for m_code, (score, area, pop) in accessibility.items():
        if area not in area_stats:
            area_stats[area] = {"scores": [], "pops": [], "zero_pop": 0}
        area_stats[area]["scores"].append(score)
        area_stats[area]["pops"].append(pop)
        if score == 0:
            area_stats[area]["zero_pop"] += pop

    print(f"\n  {'医療圏':<12} {'平均スコア':>12} {'最低スコア':>12} {'アクセス0人口':>12} {'メッシュ数':>8}")
    print(f"  {'-'*60}")

    results = []
    for area in sorted(area_stats.keys(), key=lambda a: sum(area_stats[a]["pops"]), reverse=True):
        s = area_stats[area]
        avg = sum(s["scores"]) / len(s["scores"]) if s["scores"] else 0
        mn = min(s["scores"]) if s["scores"] else 0
        results.append({
            "area": area, "avg": avg, "min": mn,
            "zero_pop": s["zero_pop"], "count": len(s["scores"])
        })
        print(f"  {area or '不明':<12} {avg:>12.6f} {mn:>12.6f} {s['zero_pop']:>10,}人 {len(s['scores']):>8}")

    # 全体の空白地帯
    total_zero = sum(s["zero_pop"] for s in area_stats.values())
    total_pop = sum(sum(s["pops"]) for s in area_stats.values())
    print(f"\n  アクセス空白地帯人口: {total_zero:,}人 / {total_pop:,}人 ({total_zero/total_pop*100:.1f}%)")

    conn.close()
    return results


if __name__ == "__main__":
    chiba_db = Path.home() / "chiba_pdf_db" / "chiba_iryo.db"
    osaka_db = Path.home() / "osaka_pdf_db" / "osaka_iryo.db"

    for db_path in [chiba_db, osaka_db]:
        if not db_path.exists():
            continue
        # 薬局アクセシビリティ（2km圏）
        run_2sfca(db_path, "pharmacies", 2.0, f"{db_path.parent.name} 薬局")

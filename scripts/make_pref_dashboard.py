#!/usr/bin/env python3
"""
指定した都道府県のダッシュボードHTMLを生成する
使い方: python3 make_pref_dashboard.py --code 13
"""

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path

PREF_NAMES = {
    1:"北海道",2:"青森県",3:"岩手県",4:"宮城県",5:"秋田県",6:"山形県",7:"福島県",
    8:"茨城県",9:"栃木県",10:"群馬県",11:"埼玉県",12:"千葉県",13:"東京都",14:"神奈川県",
    15:"新潟県",16:"富山県",17:"石川県",18:"福井県",19:"山梨県",20:"長野県",
    21:"岐阜県",22:"静岡県",23:"愛知県",24:"三重県",
    25:"滋賀県",26:"京都府",27:"大阪府",28:"兵庫県",29:"奈良県",30:"和歌山県",
    31:"鳥取県",32:"島根県",33:"岡山県",34:"広島県",35:"山口県",
    36:"徳島県",37:"香川県",38:"愛媛県",39:"高知県",
    40:"福岡県",41:"佐賀県",42:"長崎県",43:"熊本県",44:"大分県",45:"宮崎県",46:"鹿児島県",47:"沖縄県",
}

FUNCTIONS = [
    ("all", "全薬局アクセス"),
    ("func_kakaritsuke", "かかりつけ薬剤師"),
    ("func_chiiki_shien", "地域支援体制"),
    ("func_zaitaku_sogo", "在宅薬学総合"),
    ("func_mukin", "無菌製剤処理"),
    ("func_zaitaku_cv", "在宅中心静脈栄養"),
    ("func_zaitaku_mayaku", "在宅医療用麻薬"),
    ("func_medical_dx", "医療DX推進"),
    ("func_generic", "後発医薬品調剤体制"),
    ("func_renkei_kyoka", "連携強化"),
]


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2)
    return R * 2 * math.asin(math.sqrt(a))


def gaussian_weight(d, t):
    if d > t: return 0
    b = t/2; return math.exp(-(d**2)/(b**2))


def run_2sfca(meshes, supplies, threshold):
    ratios = {}
    for s_id, s_lat, s_lon in supplies:
        wp = sum(gaussian_weight(haversine_km(s_lat, s_lon, m[1], m[2]), threshold) * m[3] for m in meshes)
        ratios[s_id] = 1.0/wp if wp > 0 else 0
    access = {}
    for m in meshes:
        sc = sum(gaussian_weight(haversine_km(m[1], m[2], s[1], s[2]), threshold) * ratios.get(s[0],0) for s in supplies)
        access[m[0]] = sc
    return access


def get_db_path(code):
    pcode = f"{code:02d}"
    name = PREF_NAMES[code]
    for c in [
        Path.home() / "chiba_pdf_db" / "chiba_iryo.db" if code == 12 else None,
        Path.home() / "osaka_pdf_db" / "osaka_iryo.db" if code == 27 else None,
        Path.home() / f"prefdb_{pcode}_{name}" / f"{pcode}_iryo.db",
    ]:
        if c and c.exists():
            return c
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", type=int, required=True)
    args = parser.parse_args()

    code = args.code
    pcode = f"{code:02d}"
    name = PREF_NAMES.get(code, "不明")
    db_path = get_db_path(code)
    if not db_path:
        print(f"ERROR: DB not found for {name}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT mesh_code, lat, lon, population, COALESCE(medical_area, municipality),
               pop_2025, pop_2030, pop_2035, pop_2040, pop_2050,
               elderly_65_2025, elderly_75_2025,
               elderly_65_2030, elderly_75_2030,
               elderly_65_2035, elderly_75_2035,
               elderly_65_2040, elderly_75_2040,
               elderly_65_2050, elderly_75_2050
        FROM population_mesh WHERE population >= 100 AND lat > 1
    """)
    meshes = cur.fetchall()

    cur.execute("SELECT id, lat, lon FROM pharmacies WHERE lat > 1 AND lon > 1")
    all_supplies = [(r[0], r[1], r[2]) for r in cur.fetchall()]

    # Check which function columns exist
    cur.execute("PRAGMA table_info(pharmacies)")
    existing_cols = {r[1] for r in cur.fetchall()}

    available_functions = [("all", "全薬局アクセス")]
    for fc, fl in FUNCTIONS[1:]:
        if fc in existing_cols:
            cur.execute(f"SELECT COUNT(*) FROM pharmacies WHERE {fc}=1")
            if cur.fetchone()[0] > 0:
                available_functions.append((fc, fl))

    print(f"=== {name} ダッシュボード ===")
    print(f"  メッシュ: {len(meshes)}, 薬局: {len(all_supplies)}")
    print(f"  機能: {len(available_functions)}種")

    # Compute 2SFCA for all available functions
    scores = {}
    medians = {}

    for fc, fl in available_functions:
        if fc == "all":
            sups = all_supplies
        else:
            cur.execute(f"SELECT id, lat, lon FROM pharmacies WHERE lat > 1 AND lon > 1 AND {fc}=1")
            sups = [(r[0], r[1], r[2]) for r in cur.fetchall()]
        if not sups:
            continue
        print(f"  {fl}: {len(sups)}件...")
        access = run_2sfca(meshes, sups, 5.0)
        scores[fc] = access
        vals = sorted([v for v in access.values() if v > 0])
        medians[fc] = vals[len(vals)//2] if vals else 0.0001

    conn.close()

    # Build mesh JSON
    mesh_data = []
    for row in meshes:
        mc = row[0]
        def r(v): return round(v) if v else 0
        entry = {
            "lat": round(row[1], 5), "lon": round(row[2], 5),
            "pop": r(row[3]), "area": row[4] or "不明",
            "pt": [r(row[3]), r(row[5]), r(row[6]), r(row[7]), r(row[8]), r(row[9])],
            "e65": [r(row[10]), r(row[12]), r(row[14]), r(row[16]), r(row[18])],
            "e75": [r(row[11]), r(row[13]), r(row[15]), r(row[17]), r(row[19])],
            "s": {},
        }
        for fc, _ in available_functions:
            entry["s"][fc] = round(scores.get(fc, {}).get(mc, 0), 8)
        mesh_data.append(entry)

    medians_json = {k: round(v, 8) for k, v in medians.items()}

    # HTML
    options_html = "".join(f'<option value="{fc}">{fl}</option>' for fc, fl in available_functions)

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>CrossHealth {name} 薬局機能ダッシュボード</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
body {{ margin:0; font-family: -apple-system, sans-serif; }}
#map {{ height:100vh; width:100%; }}
#controls {{
  position:fixed; top:10px; right:10px; z-index:1000;
  background:white; padding:12px 16px; border-radius:8px;
  box-shadow:0 2px 8px rgba(0,0,0,0.3); font-size:13px; min-width:220px;
}}
#controls select {{ width:100%; padding:6px; font-size:14px; margin:6px 0; }}
#controls .stat {{ margin-top:8px; font-size:12px; color:#555; }}
#legend {{
  position:fixed; bottom:20px; left:20px; z-index:1000;
  background:white; padding:10px 14px; border-radius:8px;
  box-shadow:0 2px 6px rgba(0,0,0,0.3); font-size:12px; line-height:1.8;
}}
.dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:4px; }}
</style>
</head><body>
<div id="map"></div>
<div id="controls">
  <b>CrossHealth {name}</b><br>
  <small>薬局機能ダッシュボード</small>
  <select id="funcSelect" onchange="updateLayer()">
    {options_html}
  </select>
  <div class="stat" id="statBox"></div>
</div>
<div id="legend">
  <span class="dot" style="background:#4caf50"></span>充足<br>
  <span class="dot" style="background:#fdd835"></span>やや不足<br>
  <span class="dot" style="background:#ff9800"></span>不足<br>
  <span class="dot" style="background:#d32f2f"></span><b>機能空白</b><br>
  <span class="dot" style="background:#9e9e9e"></span>薬局なし
</div>
<script>
var meshData = {json.dumps(mesh_data)};
var medians = {json.dumps(medians_json)};
var map = L.map('map').setView([{meshes[0][1]:.4f},{meshes[0][2]:.4f}], 10);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}@2x.png', {{
  attribution: '&copy; OpenStreetMap &copy; CARTO | CrossHealth Healthcare DB',
  maxZoom: 18
}}).addTo(map);
var lats=meshData.map(d=>d.lat),lons=meshData.map(d=>d.lon);
map.fitBounds([[Math.min(...lats),Math.min(...lons)],[Math.max(...lats),Math.max(...lons)]]);
var circles=[];
function getColor(sf,sa,med){{if(sf===0)return sa>0?['#d32f2f',0.7]:['#9e9e9e',0.15];if(sf<med*0.3)return['#ff9800',0.55];if(sf<med)return['#fdd835',0.4];return['#4caf50',0.3]}}
function updateLayer(){{var f=document.getElementById('funcSelect').value;var med=medians[f]||0.0001;var gP=0,tP=0;circles.forEach(function(c,i){{var d=meshData[i];var sf=d.s[f]||0;var sa=d.s['all']||0;var co=getColor(sf,sa,med);c.setStyle({{fillColor:co[0],color:co[0],fillOpacity:co[1]}});tP+=d.pop;if(sa>0&&sf===0)gP+=d.pop}});var pct=tP>0?(gP/tP*100).toFixed(1):'0.0';document.getElementById('statBox').innerHTML='機能空白人口: <b>'+gP.toLocaleString()+'人</b> ('+pct+'%)<br>対象人口: '+tP.toLocaleString()+'人'}}
meshData.forEach(function(d){{var sa=d.s['all']||0;var co=getColor(sa,1,medians['all']);var yrs=['2020','2025','2030','2035','2040','2050'];var pt=d.pt;var chg=pt[0]>0&&pt[5]>0?((pt[5]-pt[0])/pt[0]*100).toFixed(0):'?';var rows='<tr>';for(var j=0;j<6;j++)rows+='<td style=\"text-align:right;font-size:10px\">'+yrs[j]+'</td>';rows+='</tr><tr>';for(var j=0;j<6;j++)rows+='<td style=\"text-align:right\">'+pt[j].toLocaleString()+'人</td>';rows+='</tr>';var e75=d.e75;var eRows='<tr>';for(var j=0;j<5;j++)eRows+='<td style=\"text-align:right\">'+(e75[j]||0).toLocaleString()+'人</td>';eRows+='</tr>';var html='<div style=\"font-size:12px\"><b>'+d.area+'</b> 2050年'+chg+'%<br><table cellpadding=\"1\">'+rows+'</table><small>75歳+（2025-2050）</small><table cellpadding=\"1\"><tr><td style=\"font-size:10px\">2025</td><td style=\"font-size:10px\">2030</td><td style=\"font-size:10px\">2035</td><td style=\"font-size:10px\">2040</td><td style=\"font-size:10px\">2050</td></tr>'+eRows+'</table></div>';var c=L.circleMarker([d.lat,d.lon],{{radius:4,weight:0.3,color:co[0],fillColor:co[0],fillOpacity:co[1]}}).bindPopup(html,{{maxWidth:350}}).addTo(map);circles.push(c)}});updateLayer();
</script>
</body></html>"""

    out_dir = db_path.parent
    out_path = out_dir / f"dashboard_{pcode}_{name}.html"
    out_path.write_text(html, encoding="utf-8")
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"  保存: {out_path} ({size_mb:.1f}MB)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
薬局機能ダッシュボード（軽量版）
メッシュデータをGeoJSONとしてJavaScriptに埋め込み、
ドロップダウンで機能を切り替える方式
+ 二次医療圏境界線オーバーレイ
+ ポップアップ内SVG人口推移チャート
"""

import json
import math
import sqlite3
from pathlib import Path

try:
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

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

# 千葉県 医療圏マッピング（市区町村コード→医療圏名）
CHIBA_IRYO_KEN = {
    12101: "千葉", 12102: "千葉", 12103: "千葉", 12104: "千葉", 12105: "千葉", 12106: "千葉",
    12203: "東葛南部", 12204: "東葛南部", 12207: "東葛南部", 12216: "東葛南部", 12221: "東葛南部", 12224: "東葛南部", 12227: "東葛南部",
    12208: "東葛北部", 12217: "東葛北部", 12220: "東葛北部", 12222: "東葛北部", 12231: "東葛北部", 12232: "東葛北部",
    12211: "印旛", 12212: "印旛", 12228: "印旛", 12230: "印旛", 12233: "印旛", 12322: "印旛", 12329: "印旛",
    12202: "香取海匝", 12215: "香取海匝", 12235: "香取海匝", 12236: "香取海匝", 12342: "香取海匝", 12347: "香取海匝", 12349: "香取海匝",
    12210: "山武長生夷隅", 12213: "山武長生夷隅", 12218: "山武長生夷隅", 12237: "山武長生夷隅", 12238: "山武長生夷隅", 12239: "山武長生夷隅",
    12403: "山武長生夷隅", 12409: "山武長生夷隅", 12410: "山武長生夷隅", 12421: "山武長生夷隅", 12422: "山武長生夷隅", 12423: "山武長生夷隅",
    12424: "山武長生夷隅", 12426: "山武長生夷隅", 12427: "山武長生夷隅", 12441: "山武長生夷隅", 12443: "山武長生夷隅",
    12205: "安房", 12223: "安房", 12234: "安房", 12463: "安房",
    12206: "君津", 12225: "君津", 12226: "君津", 12229: "君津",
    12219: "市原",
}

# 大阪府 医療圏マッピング
OSAKA_IRYO_KEN = {
    27102: "大阪市", 27103: "大阪市", 27104: "大阪市", 27106: "大阪市", 27107: "大阪市", 27108: "大阪市",
    27109: "大阪市", 27111: "大阪市", 27113: "大阪市", 27114: "大阪市", 27115: "大阪市", 27116: "大阪市",
    27117: "大阪市", 27118: "大阪市", 27119: "大阪市", 27120: "大阪市", 27121: "大阪市", 27122: "大阪市",
    27123: "大阪市", 27124: "大阪市", 27125: "大阪市", 27126: "大阪市", 27127: "大阪市", 27128: "大阪市",
    27141: "堺市", 27142: "堺市", 27143: "堺市", 27144: "堺市", 27145: "堺市", 27146: "堺市", 27147: "堺市",
    27203: "豊能", 27204: "豊能", 27220: "豊能", 27321: "豊能", 27322: "豊能",
    27205: "三島", 27207: "三島", 27211: "三島", 27224: "三島", 27301: "三島",
    27210: "北河内", 27215: "北河内", 27209: "北河内", 27223: "北河内", 27229: "北河内", 27218: "北河内", 27230: "北河内",
    27227: "中河内", 27212: "中河内", 27221: "中河内",
    27214: "南河内", 27216: "南河内", 27217: "南河内", 27222: "南河内", 27226: "南河内", 27231: "南河内", 27381: "南河内", 27382: "南河内", 27383: "南河内",
    27202: "泉州", 27206: "泉州", 27208: "泉州", 27213: "泉州", 27219: "泉州", 27225: "泉州", 27228: "泉州", 27232: "泉州", 27341: "泉州", 27361: "泉州", 27362: "泉州", 27366: "泉州",
}

# GeoJSONパスと医療圏マッピングの対応
BOUNDARY_CONFIG = {
    "chiba": {
        "geojson": Path.home() / "chiba_pdf_db" / "N03-20240101_12.geojson",
        "mapping": CHIBA_IRYO_KEN,
        "simplify": 0.005,
    },
    "osaka": {
        "geojson": Path.home() / "osaka_pdf_db" / "N03-20240101_27.geojson",
        "mapping": OSAKA_IRYO_KEN,
        "simplify": 0.003,
    },
}


def build_boundary_geojson(label):
    """市区町村GeoJSONから医療圏境界線GeoJSONを生成"""
    cfg = BOUNDARY_CONFIG.get(label)
    if not cfg or not cfg["geojson"].exists():
        print(f"  境界線GeoJSON: {cfg['geojson'] if cfg else '設定なし'} が見つかりません")
        return None
    if not HAS_SHAPELY:
        print("  shapely未インストール: 境界線スキップ")
        return None

    with open(cfg["geojson"], encoding="utf-8") as f:
        gj = json.load(f)

    iryo_map = cfg["mapping"]
    groups = {}
    for feat in gj["features"]:
        code = feat["properties"].get("N03_007")
        if not code:
            continue
        code_int = int(code)
        area = iryo_map.get(code_int)
        if not area:
            continue
        if area not in groups:
            groups[area] = []
        try:
            geom = shape(feat["geometry"])
            if geom.is_valid:
                groups[area].append(geom)
            else:
                geom = geom.buffer(0)
                if geom.is_valid:
                    groups[area].append(geom)
        except Exception:
            pass

    features = []
    for area_name, geoms in groups.items():
        merged = unary_union(geoms)
        simplified = merged.simplify(cfg["simplify"], preserve_topology=True)
        centroid = merged.centroid
        geom_json = mapping(simplified)
        # 座標の桁数を削減（ファイルサイズ圧縮）
        geom_str = json.dumps(geom_json)
        # round coords to 4 decimal places
        geom_json = json.loads(geom_str)
        _round_coords(geom_json)
        features.append({
            "type": "Feature",
            "properties": {
                "name": area_name,
                "cx": round(centroid.x, 4),
                "cy": round(centroid.y, 4),
            },
            "geometry": geom_json,
        })

    result = {"type": "FeatureCollection", "features": features}
    size_kb = len(json.dumps(result)) / 1024
    print(f"  境界線GeoJSON: {len(features)}医療圏 ({size_kb:.0f}KB)")
    return result


def _round_coords(geom_json):
    """GeoJSON座標を小数4桁に丸める"""
    def _round_ring(coords):
        if isinstance(coords[0], (int, float)):
            return [round(c, 4) for c in coords]
        return [_round_ring(c) for c in coords]

    if "coordinates" in geom_json:
        geom_json["coordinates"] = _round_ring(geom_json["coordinates"])


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def gaussian_weight(d, t):
    if d > t:
        return 0
    b = t / 2
    return math.exp(-(d ** 2) / (b ** 2))


def run_2sfca(meshes, supplies, threshold):
    ratios = {}
    for s_id, s_lat, s_lon in supplies:
        wp = sum(
            gaussian_weight(haversine_km(s_lat, s_lon, m[1], m[2]), threshold) * m[3]
            for m in meshes
        )
        ratios[s_id] = 1.0 / wp if wp > 0 else 0
    access = {}
    for m in meshes:
        sc = sum(
            gaussian_weight(haversine_km(m[1], m[2], s[1], s[2]), threshold)
            * ratios.get(s[0], 0)
            for s in supplies
        )
        access[m[0]] = sc
    return access


def build(db_path, label, output_dir):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT mesh_code, lat, lon, population, medical_area,
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

    print(f"\n=== {label} === メッシュ:{len(meshes)} 薬局:{len(all_supplies)}")

    # 境界線GeoJSON生成
    boundary_gj = build_boundary_geojson(label)

    # 全機能の2SFCAを計算
    scores = {}
    medians = {}

    for func_col, func_label in FUNCTIONS:
        if func_col == "all":
            sups = all_supplies
        else:
            cur.execute(f"SELECT id, lat, lon FROM pharmacies WHERE lat > 1 AND lon > 1 AND {func_col}=1")
            sups = [(r[0], r[1], r[2]) for r in cur.fetchall()]

        if not sups:
            print(f"  {func_label}: 0件 skip")
            scores[func_col] = {m[0]: 0 for m in meshes}
            medians[func_col] = 0.0001
            continue

        print(f"  {func_label}: {len(sups)}件 計算中...")
        access = run_2sfca(meshes, sups, 5.0)
        scores[func_col] = access

        vals = sorted([v for v in access.values() if v > 0])
        medians[func_col] = vals[len(vals) // 2] if vals else 0.0001

    conn.close()

    # メッシュデータをJSONに変換
    mesh_data = []
    for row in meshes:
        mc, lat, lon, pop, area = row[0], row[1], row[2], row[3], row[4]
        p25, p30, p35, p40, p50 = row[5], row[6], row[7], row[8], row[9]
        e65_25, e75_25 = row[10], row[11]
        e65_30, e75_30 = row[12], row[13]
        e65_35, e75_35 = row[14], row[15]
        e65_40, e75_40 = row[16], row[17]
        e65_50, e75_50 = row[18], row[19]

        def r(v): return round(v) if v else 0

        entry = {
            "lat": round(lat, 5), "lon": round(lon, 5),
            "pop": r(pop), "area": area or "不明",
            "pt": [r(pop), r(p25), r(p30), r(p35), r(p40), r(p50)],
            "e65": [r(e65_25), r(e65_30), r(e65_35), r(e65_40), r(e65_50)],
            "e75": [r(e75_25), r(e75_30), r(e75_35), r(e75_40), r(e75_50)],
            "s": {},
        }
        for func_col, _ in FUNCTIONS:
            sc = scores[func_col].get(mc, 0)
            entry["s"][func_col] = round(sc, 8)
        mesh_data.append(entry)

    medians_json = {k: round(v, 8) for k, v in medians.items()}

    boundary_json_str = json.dumps(boundary_gj) if boundary_gj else "null"

    # HTML生成
    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>CrossHealth 薬局機能ダッシュボード - {label}</title>
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
.iryo-label {{
  font-size:11px; font-weight:bold; color:#333; text-shadow:1px 1px 2px #fff, -1px -1px 2px #fff, 1px -1px 2px #fff, -1px 1px 2px #fff;
  white-space:nowrap; pointer-events:none;
}}
</style>
</head><body>
<div id="map"></div>
<div id="controls">
  <b>CrossHealth 薬局機能ダッシュボード</b><br>
  <small>{label.upper()}</small>
  <select id="funcSelect" onchange="updateLayer()">
    {"".join(f'<option value="{fc}">{fl}</option>' for fc, fl in FUNCTIONS)}
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
var boundaryData = {boundary_json_str};
var allScoreKey = "all";

var map = L.map('map').setView([{meshes[0][1]:.4f},{meshes[0][2]:.4f}], 10);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}@2x.png', {{
  attribution: '&copy; OpenStreetMap &copy; CARTO | CrossHealth Healthcare DB',
  maxZoom: 18
}}).addTo(map);

var lats = meshData.map(d=>d.lat), lons = meshData.map(d=>d.lon);
map.fitBounds([[Math.min(...lats),Math.min(...lons)],[Math.max(...lats),Math.max(...lons)]]);

// --- 二次医療圏境界線 ---
if (boundaryData) {{
  L.geoJSON(boundaryData, {{
    style: function() {{
      return {{ color: '#333', weight: 1.5, fill: false, opacity: 0.7, dashArray: '4 2' }};
    }}
  }}).addTo(map);
  // 医療圏ラベル
  boundaryData.features.forEach(function(f) {{
    var p = f.properties;
    L.marker([p.cy, p.cx], {{
      icon: L.divIcon({{
        className: 'iryo-label',
        html: p.name,
        iconSize: null,
        iconAnchor: [0, 0]
      }})
    }}).addTo(map);
  }});
}}

// --- SVG棒グラフ生成関数 ---
function makeSvgBar(values, labels, title, w, h) {{
  var maxVal = Math.max.apply(null, values.filter(function(v){{return v>0}}));
  if (maxVal === 0) return '';
  var barH = Math.floor((h - 18) / values.length);
  var baseVal = values[0];
  var svg = '<svg width="'+w+'" height="'+h+'" style="display:block;margin:4px 0">';
  svg += '<text x="0" y="12" font-size="10" font-weight="bold" fill="#333">'+title+'</text>';
  for (var i=0; i<values.length; i++) {{
    var y = 18 + i * barH;
    var bw = Math.max(2, Math.round(values[i] / maxVal * (w - 90)));
    var ratio = baseVal > 0 ? (values[i] - baseVal) / baseVal : 0;
    var col;
    if (ratio >= 0) {{
      var b = Math.min(255, Math.round(100 + ratio * 400));
      col = 'rgb('+Math.max(0,100-Math.round(ratio*200))+','+Math.max(0,130-Math.round(ratio*200))+','+b+')';
    }} else {{
      var r = Math.min(255, Math.round(180 + Math.abs(ratio) * 200));
      col = 'rgb('+r+','+Math.max(0,Math.round(100-Math.abs(ratio)*150))+','+Math.max(0,Math.round(100-Math.abs(ratio)*150))+')';
    }}
    svg += '<rect x="0" y="'+y+'" width="'+bw+'" height="'+(barH-2)+'" fill="'+col+'" rx="1"/>';
    svg += '<text x="'+(bw+3)+'" y="'+(y+barH-4)+'" font-size="9" fill="#555">'+values[i].toLocaleString()+'人 ('+labels[i]+')</text>';
  }}
  svg += '</svg>';
  return svg;
}}

var circles = [];

function getColor(scFunc, scAll, median) {{
  if (scFunc === 0) {{
    return scAll > 0 ? ['#d32f2f', 0.7] : ['#9e9e9e', 0.15];
  }} else if (scFunc < median * 0.3) {{
    return ['#ff9800', 0.55];
  }} else if (scFunc < median) {{
    return ['#fdd835', 0.4];
  }} else {{
    return ['#4caf50', 0.3];
  }}
}}

function updateLayer() {{
  var func = document.getElementById('funcSelect').value;
  var med = medians[func] || 0.0001;
  var gapPop = 0, totalPop = 0;

  circles.forEach(function(c, i) {{
    var d = meshData[i];
    var scFunc = d.s[func] || 0;
    var scAll = d.s[allScoreKey] || 0;
    var co = getColor(scFunc, scAll, med);
    c.setStyle({{ fillColor: co[0], color: co[0], fillOpacity: co[1] }});
    totalPop += d.pop;
    if (scAll > 0 && scFunc === 0) gapPop += d.pop;
  }});

  var pct = totalPop > 0 ? (gapPop/totalPop*100).toFixed(1) : '0.0';
  document.getElementById('statBox').innerHTML =
    '機能空白人口: <b>' + gapPop.toLocaleString() + '人</b> (' + pct + '%)<br>' +
    '対象人口: ' + totalPop.toLocaleString() + '人';
}}

// 初期描画
meshData.forEach(function(d) {{
  var scAll = d.s[allScoreKey] || 0;
  var co = getColor(scAll, 1, medians[allScoreKey]);
  var yrs = ['2020','2025','2030','2035','2040','2050'];
  var eYrs = ['2025','2030','2035','2040','2050'];
  var pt = d.pt;
  var chg50 = pt[0] > 0 ? ((pt[5]-pt[0])/pt[0]*100).toFixed(0) : '?';

  // テキストテーブル
  var popRows = '<tr><td><b>総人口</b></td>';
  for(var j=0;j<6;j++) popRows += '<td style="text-align:right">' + pt[j].toLocaleString() + '人</td>';
  popRows += '</tr>';
  var e65 = d.e65, e75 = d.e75;
  var e65Rows = '<tr><td>65歳+</td>';
  for(var j=0;j<5;j++) e65Rows += '<td style="text-align:right">' + (e65[j]||0).toLocaleString() + '人</td>';
  e65Rows += '</tr>';
  var e75Rows = '<tr><td>75歳+</td>';
  for(var j=0;j<5;j++) e75Rows += '<td style="text-align:right">' + (e75[j]||0).toLocaleString() + '人</td>';
  e75Rows += '</tr>';
  var hdr = '<tr><td></td>';
  for(var j=0;j<6;j++) hdr += '<td style="text-align:right;font-size:10px;color:#888">' + yrs[j] + '</td>';
  hdr += '</tr>';
  var eHdr = '<tr><td></td>';
  for(var j=1;j<6;j++) eHdr += '<td style="text-align:right;font-size:10px;color:#888">' + yrs[j] + '</td>';
  eHdr += '</tr>';

  // SVGチャート
  var popSvg = makeSvgBar(pt, yrs, '人口推移', 260, 112);
  var e75Svg = makeSvgBar(e75, eYrs, '75歳以上人口', 220, 98);

  var html = '<div style="font-size:12px;min-width:280px">' +
    '<b>' + d.area + '</b>  <span style="color:#888">2050年' + chg50 + '%</span><br>' +
    popSvg +
    '<table style="border-collapse:collapse;margin:4px 0;font-size:11px" cellpadding="2">' +
    hdr + popRows + '</table>' +
    e75Svg +
    '<table style="border-collapse:collapse;margin:4px 0;font-size:11px" cellpadding="2">' +
    eHdr + e65Rows + e75Rows + '</table></div>';
  var c = L.circleMarker([d.lat, d.lon], {{
    radius: 4, weight: 0.3, color: co[0],
    fillColor: co[0], fillOpacity: co[1]
  }}).bindPopup(html, {{maxWidth: 420}}).addTo(map);
  circles.push(c);
}});
updateLayer();
</script>
</body></html>"""

    path = output_dir / f"dashboard_{label}.html"
    path.write_text(html, encoding="utf-8")
    size_mb = path.stat().st_size / 1024 / 1024
    print(f"  保存: {path} ({size_mb:.1f}MB)")
    if size_mb > 5:
        print(f"  ⚠ 警告: ファイルサイズが5MBを超えています")


if __name__ == "__main__":
    for db_name, label, out_dir in [
        ("chiba_pdf_db/chiba_iryo.db", "chiba", Path.home() / "chiba_pdf_db"),
        ("osaka_pdf_db/osaka_iryo.db", "osaka", Path.home() / "osaka_pdf_db"),
    ]:
        db = Path.home() / db_name
        if not db.exists():
            continue
        build(db, label, out_dir)

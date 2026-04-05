#!/usr/bin/env python3
"""
全国ダッシュボードv2: 6レイヤー切替式の地域医療インフラ可視化
make_dashboard_lite.py と同じアプローチ（JSON埋め込み＋JS側で色を動的変更）
"""

import json
import sqlite3
from pathlib import Path
from collections import defaultdict

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

PREF_LIST = [PREF_NAMES[k] for k in sorted(PREF_NAMES.keys())]


def get_db_path(code):
    pcode = f"{code:02d}"
    name = PREF_NAMES[code]
    if code == 12:
        p = Path.home() / "chiba_pdf_db" / "chiba_iryo.db"
        if p.exists():
            return p
    if code == 27:
        p = Path.home() / "osaka_pdf_db" / "osaka_iryo.db"
        if p.exists():
            return p
    p = Path.home() / f"prefdb_{pcode}_{name}" / f"{pcode}_iryo.db"
    return p if p.exists() else None


def pctile(values, probs=(0.05, 0.25, 0.5, 0.75, 0.95)):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return [0.0] * len(probs)
    return [s[min(int(p * n), n - 1)] for p in probs]


def collect_data():
    """全都道府県からメッシュデータと薬局データを収集"""
    all_meshes = []
    total_pharma = 0

    for code in sorted(PREF_NAMES.keys()):
        db_path = get_db_path(code)
        if not db_path:
            print(f"  {PREF_NAMES[code]}: DB未検出 skip")
            continue

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # 薬局の座標取得
        try:
            cur.execute("SELECT lat, lon FROM pharmacies WHERE lat > 1 AND lon > 1")
            pharms = cur.fetchall()
            total_pharma += len(pharms)
        except Exception:
            pharms = []

        # メッシュデータ取得 (人口200人以上)
        try:
            cur.execute("""
                SELECT mesh_code, lat, lon, population,
                       pop_2025, pop_2030, pop_2035, pop_2040, pop_2050,
                       elderly_75_2025, elderly_75_2030, elderly_75_2035,
                       elderly_75_2040, elderly_75_2050,
                       access_phar_5km
                FROM population_mesh WHERE population >= 200 AND lat > 1
            """)
            meshes = cur.fetchall()
        except Exception:
            meshes = []

        conn.close()
        if not meshes:
            continue

        # 空間インデックス構築（薬局→メッシュ割当用）
        grid = defaultdict(list)
        for i, m in enumerate(meshes):
            gk = (int(m[1] * 100), int(m[2] * 100))
            grid[gk].append(i)

        pcnt = defaultdict(int)
        for plat, plon in pharms:
            gk = (int(plat * 100), int(plon * 100))
            best, bdist = None, 1e9
            for d0 in (-1, 0, 1):
                for d1 in (-1, 0, 1):
                    for i in grid.get((gk[0] + d0, gk[1] + d1), []):
                        dist = (plat - meshes[i][1]) ** 2 + (plon - meshes[i][2]) ** 2
                        if dist < bdist:
                            bdist = dist
                            best = i
            if best is not None and bdist < 0.0003:
                pcnt[best] += 1

        pidx = sorted(PREF_NAMES.keys()).index(code)
        for i, m in enumerate(meshes):
            def r(v):
                return round(v) if v else 0
            all_meshes.append([
                round(m[1], 4), round(m[2], 4), pidx,
                r(m[3]),
                [r(m[3]), r(m[4]), r(m[5]), r(m[6]), r(m[7]), r(m[8])],
                [r(m[9]), r(m[10]), r(m[11]), r(m[12]), r(m[13])],
                round(m[14], 8) if m[14] else 0,
                pcnt.get(i, 0),
            ])

        print(f"  {PREF_NAMES[code]}: {len(pharms)}薬局, {len(meshes)}メッシュ, 累計{len(all_meshes)}")

    return all_meshes, total_pharma


def compute_quantiles(meshes):
    """各レイヤーの色分け用パーセンタイルを計算"""
    # 薬局密度 (人口1万人あたり)
    pd_vals = [m[7] / m[3] * 10000 for m in meshes if m[3] > 0 and m[7] > 0]

    # 人口 2020
    pop_vals = [m[3] for m in meshes if m[3] > 0]

    # 人口変化率 (%)
    chg_vals = [(m[4][5] - m[4][0]) / m[4][0] * 100
                for m in meshes if m[4][0] > 0]

    # 75歳以上 2025
    e75_vals = [m[5][0] for m in meshes if m[5][0] > 0]

    # 75歳以上変化率 (%)
    echg_vals = [(m[5][4] - m[5][0]) / m[5][0] * 100
                 for m in meshes if m[5][0] > 0]

    # 2SFCAスコア
    ac_vals = [m[6] for m in meshes if m[6] > 0]

    # divergingレイヤーはp95絶対値を使う
    chg_abs = sorted([abs(v) for v in chg_vals]) if chg_vals else [50]
    echg_abs = sorted([abs(v) for v in echg_vals]) if echg_vals else [50]

    return {
        "pharm_density": [round(v, 4) for v in pctile(pd_vals)],
        "pop_2020": [round(v, 1) for v in pctile(pop_vals)],
        "pop_change": [round(chg_abs[min(int(0.95 * len(chg_abs)), len(chg_abs) - 1)], 2)],
        "elderly_2025": [round(v, 1) for v in pctile(e75_vals)],
        "elderly_change": [round(echg_abs[min(int(0.95 * len(echg_abs)), len(echg_abs) - 1)], 2)],
        "access_2sfca": [round(v, 8) for v in pctile(ac_vals)],
    }


def build_html(meshes, total_pharma, output_path):
    q = compute_quantiles(meshes)
    total_pop = sum(m[3] for m in meshes)

    mesh_json = json.dumps(meshes, separators=(',', ':'))
    pref_json = json.dumps(PREF_LIST, ensure_ascii=False)
    q_json = json.dumps(q)

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>CrossHealth 全国医療インフラ ダッシュボード</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
body{{margin:0;font-family:-apple-system,'Helvetica Neue',sans-serif;}}
#map{{height:100vh;width:100%;}}
#controls{{
  position:fixed;top:10px;right:10px;z-index:1000;
  background:white;padding:14px 18px;border-radius:10px;
  box-shadow:0 2px 12px rgba(0,0,0,0.25);font-size:13px;
  min-width:260px;max-width:320px;
}}
#controls h2{{margin:0 0 4px 0;font-size:16px;}}
.sub{{font-size:11px;color:#888;margin-bottom:10px;}}
#controls select{{
  width:100%;padding:7px;font-size:13px;margin:6px 0;
  border:1px solid #ccc;border-radius:5px;cursor:pointer;
}}
#statBox{{margin-top:8px;font-size:12px;color:#555;line-height:1.7;}}
#legend{{
  position:fixed;bottom:20px;left:20px;z-index:1000;
  background:white;padding:12px 16px;border-radius:8px;
  box-shadow:0 2px 6px rgba(0,0,0,0.3);font-size:12px;
}}
.leg-title{{font-weight:bold;margin-bottom:6px;font-size:11px;color:#333;}}
.grad-bar{{width:180px;height:14px;border-radius:3px;margin:4px 0;}}
.grad-labels{{display:flex;justify-content:space-between;font-size:10px;color:#666;width:180px;}}
.leg-extra{{margin-top:5px;font-size:11px;color:#666;display:flex;align-items:center;gap:4px;}}
.leg-swatch{{display:inline-block;width:12px;height:12px;border-radius:2px;}}
</style>
</head><body>
<div id="map"></div>
<div id="controls">
  <h2>CrossHealth</h2>
  <div class="sub">全国医療インフラ ダッシュボード</div>
  <select id="layerSelect" onchange="updateLayer()">
    <option value="pharm_density">薬局・DS分布（人口あたり）</option>
    <option value="pop_2020">人口分布（2020年）</option>
    <option value="pop_change">人口変化（2020→2050）</option>
    <option value="elderly_2025">75歳以上人口（2025）</option>
    <option value="elderly_change">75歳以上人口変化（2025→2050）</option>
    <option value="access_2sfca">薬局アクセシビリティ（2SFCA）</option>
  </select>
  <div id="statBox"></div>
</div>
<div id="legend"></div>
<script>
var D={mesh_json};
var P={pref_json};
var Q={q_json};
var TPH={total_pharma};
var TPOP={total_pop};

var map=L.map('map',{{preferCanvas:true}}).setView([36.5,137.5],6);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}@2x.png',{{
  attribution:'&copy; OpenStreetMap &copy; CARTO | CrossHealth Healthcare DB',
  maxZoom:18
}}).addTo(map);

/* ---------- Color utilities ---------- */
function lerp(a,b,t){{return a+(b-a)*t;}}
function rgb(r,g,b){{return 'rgb('+Math.round(r)+','+Math.round(g)+','+Math.round(b)+')';}}
function interpStops(t,S){{
  t=Math.max(0,Math.min(1,t));
  var n=S.length-1,i=Math.min(Math.floor(t*n),n-1),f=t*n-i;
  return rgb(lerp(S[i][0],S[i+1][0],f),lerp(S[i][1],S[i+1][1],f),lerp(S[i][2],S[i+1][2],f));
}}

var BLUE=[[235,245,255],[158,202,235],[66,146,198],[8,81,156]];
var GREEN=[[237,248,233],[166,217,161],[65,171,93],[0,109,44]];
var PURPLE=[[242,240,247],[188,189,220],[128,125,186],[84,39,143]];
/* diverging: 減少(red)→白→増加(blue) */
var DIV_RB=[[178,24,43],[239,138,98],[247,247,247],[103,169,207],[33,102,172]];
/* diverging: 減少(blue)→白→増加(red) */
var DIV_BR=[[33,102,172],[103,169,207],[247,247,247],[239,138,98],[178,24,43]];
/* 2SFCA: 低(red)→黄→高(green) */
var GN_RD=[[178,24,43],[244,165,97],[247,238,180],[144,212,170],[0,109,44]];

/* ---------- Value & color per layer ---------- */
function getVal(d,ly){{
  switch(ly){{
    case 'pharm_density': return d[3]>0? d[7]/d[3]*10000 : 0;
    case 'pop_2020': return d[3];
    case 'pop_change': return d[4][0]>0? (d[4][5]-d[4][0])/d[4][0]*100 : 0;
    case 'elderly_2025': return d[5][0];
    case 'elderly_change': return d[5][0]>0? (d[5][4]-d[5][0])/d[5][0]*100 : 0;
    case 'access_2sfca': return d[6];
  }}
}}

function seqT(val,q){{
  if(q[4]-q[0]===0) return 0.5;
  return Math.max(0,Math.min(1,(val-q[0])/(q[4]-q[0])));
}}

function getColor(ly,val){{
  var q=Q[ly];
  if(ly==='pop_change'){{
    var mx=q[0]||50;
    var t=Math.max(0,Math.min(1,(val+mx)/(2*mx)));
    return [interpStops(t,DIV_RB),0.55];
  }}
  if(ly==='elderly_change'){{
    var mx=q[0]||50;
    var t=Math.max(0,Math.min(1,(val+mx)/(2*mx)));
    return [interpStops(t,DIV_BR),0.55];
  }}
  if(ly==='access_2sfca'){{
    if(val===0) return ['#bdbdbd',0.15];
    return [interpStops(seqT(val,q),GN_RD),0.5];
  }}
  if(ly==='pharm_density'){{
    if(val===0) return ['#e0e0e0',0.15];
    return [interpStops(seqT(val,q),BLUE),0.5];
  }}
  if(ly==='pop_2020'){{
    return [interpStops(seqT(val,q),GREEN),0.45];
  }}
  if(ly==='elderly_2025'){{
    if(val===0) return ['#e0e0e0',0.15];
    return [interpStops(seqT(val,q),PURPLE),0.5];
  }}
  return ['#999',0.3];
}}

/* ---------- Popup ---------- */
function makePopup(d){{
  var pref=P[d[2]], pt=d[4], e=d[5];
  var yrs=['2020','2025','2030','2035','2040','2050'];
  var eyrs=['2025','2030','2035','2040','2050'];
  var h='<div style="font-size:12px;min-width:310px">';
  h+='<b style="font-size:14px">'+pref+'</b><br>';
  /* 総人口推移 */
  h+='<table style="border-collapse:collapse;margin:6px 0;font-size:11px;width:100%" cellpadding="2">';
  h+='<tr style="color:#888;font-size:10px"><td><b>総人口</b></td>';
  for(var i=0;i<6;i++) h+='<td style="text-align:right">'+yrs[i]+'</td>';
  h+='</tr><tr><td></td>';
  for(var i=0;i<6;i++) h+='<td style="text-align:right">'+(pt[i]||0).toLocaleString()+'人</td>';
  h+='</tr></table>';
  /* 75歳以上推移 */
  h+='<table style="border-collapse:collapse;margin:4px 0;font-size:11px;width:100%" cellpadding="2">';
  h+='<tr style="color:#888;font-size:10px"><td><b>75歳以上</b></td>';
  for(var i=0;i<5;i++) h+='<td style="text-align:right">'+eyrs[i]+'</td>';
  h+='</tr><tr><td></td>';
  for(var i=0;i<5;i++) h+='<td style="text-align:right">'+(e[i]||0).toLocaleString()+'人</td>';
  h+='</tr></table>';
  h+='<div style="margin-top:4px;color:#555">薬局アクセススコア: <b>'+(d[6]>0?d[6].toFixed(6):'—')+'</b></div>';
  h+='</div>';
  return h;
}}

/* ---------- Create markers ---------- */
var circles=[];
D.forEach(function(d){{
  var c=L.circleMarker([d[0],d[1]],{{radius:2,weight:0,fillOpacity:0.5}})
    .bindPopup(function(){{return makePopup(d);}},{{maxWidth:420}})
    .addTo(map);
  circles.push(c);
}});

/* ---------- Layer update ---------- */
function updateLayer(){{
  var ly=document.getElementById('layerSelect').value;
  for(var i=0;i<D.length;i++){{
    var co=getColor(ly,getVal(D[i],ly));
    circles[i].setStyle({{fillColor:co[0],fillOpacity:co[1]}});
  }}
  document.getElementById('statBox').innerHTML=
    'メッシュ: <b>'+D.length.toLocaleString()+'</b><br>'+
    '対象人口: <b>'+TPOP.toLocaleString()+'人</b><br>'+
    '薬局数: <b>'+TPH.toLocaleString()+'</b>件';
  updateLegend(ly);
}}

/* ---------- Dynamic legend ---------- */
function gradCSS(stops){{
  var cols=[];
  for(var i=0;i<=10;i++) cols.push(interpStops(i/10,stops));
  return 'linear-gradient(to right,'+cols.join(',')+')';
}}

function updateLegend(ly){{
  var el=document.getElementById('legend');
  var cfg={{
    pharm_density:{{t:'薬局密度（人口1万人あたり）',s:BLUE,l:['少','多'],ex:null}},
    pop_2020:{{t:'人口（2020年）',s:GREEN,l:['少','多'],ex:null}},
    pop_change:{{t:'人口増減率（2020→2050）',s:DIV_RB,l:['減少','横ばい','増加'],ex:null}},
    elderly_2025:{{t:'75歳以上人口（2025年）',s:PURPLE,l:['少','多'],ex:null}},
    elderly_change:{{t:'75歳以上増減率（2025→2050）',s:DIV_BR,l:['減少','横ばい','増加'],ex:null}},
    access_2sfca:{{t:'薬局アクセシビリティ',s:GN_RD,l:['低','高'],ex:'<span class="leg-swatch" style="background:#bdbdbd"></span>データなし'}},
  }};
  var c=cfg[ly];
  var h='<div class="leg-title">'+c.t+'</div>';
  h+='<div class="grad-bar" style="background:'+gradCSS(c.s)+'"></div>';
  h+='<div class="grad-labels">';
  if(c.l.length===2){{
    h+='<span>'+c.l[0]+'</span><span>'+c.l[1]+'</span>';
  }} else {{
    h+='<span>'+c.l[0]+'</span><span>'+c.l[1]+'</span><span>'+c.l[2]+'</span>';
  }}
  h+='</div>';
  if(c.ex) h+='<div class="leg-extra">'+c.ex+'</div>';
  if(ly==='pharm_density') h+='<div class="leg-extra"><span class="leg-swatch" style="background:#e0e0e0"></span>薬局なし</div>';
  el.innerHTML=h;
}}

updateLayer();
</script>
</body></html>"""

    output_path.write_text(html, encoding="utf-8")
    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"\n保存: {output_path} ({size_mb:.1f}MB)")
    return size_mb


if __name__ == "__main__":
    print("=== 全国ダッシュボードv2 生成 ===")
    meshes, total_pharma = collect_data()
    print(f"\n合計: {len(meshes):,}メッシュ, {total_pharma:,}薬局")

    output = Path.home() / "chiba_pdf_db" / "dashboard_national.html"
    size = build_html(meshes, total_pharma, output)
    print(f"完了! ファイルサイズ: {size:.1f}MB (目標: 15MB以下)")

"""
500mメッシュ人口 × 薬局 可視化マップ生成スクリプト
output/mesh_map.html に書き出す（複数レイヤー切替対応）
"""

import json
import sqlite3
import math
from pathlib import Path
import folium

ROOT    = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "chiba_iryo.db"
OUT     = ROOT / "output" / "mesh_map.html"


def mesh_to_bounds(code: str):
    """9桁の500mメッシュコードを (lat_min, lon_min, lat_max, lon_max) に変換"""
    c = str(code).zfill(9)
    p = int(c[0:2]); q = int(c[2:4])
    lat_base = p / 1.5; lon_base = q + 100.0
    u = int(c[4]); v = int(c[5])
    lat_base += u * (2/3) / 8; lon_base += v / 8
    r = int(c[6]); s = int(c[7])
    lat_base += r * (2/3) / 80; lon_base += s / 80
    q4 = int(c[8])
    d = (2/3) / 160
    if q4 in (1, 2): lat_base += d
    if q4 in (2, 4): lon_base += 1.0 / 160
    return lat_base, lon_base, lat_base + d, lon_base + 1.0 / 160


def rate_color(rate, low_hue="blue", high_hue="red"):
    """0〜100の比率を青→赤のグラデーションに変換"""
    if rate is None or (isinstance(rate, float) and math.isnan(rate)):
        return "#dddddd"
    t = min(1.0, max(0.0, rate / 60.0))   # 60%で最大色に到達
    r = int(255 * t)
    b = int(255 * (1 - t))
    return f"#{r:02x}40{b:02x}"


def green_color(rate):
    """0〜100の比率を白→緑のグラデーション"""
    if rate is None or (isinstance(rate, float) and math.isnan(rate)):
        return "#dddddd"
    t = min(1.0, max(0.0, rate / 40.0))
    g = int(180 * t)
    return f"#40{g:02x}40"


LAYERS = [
    {
        "name": "高齢化率（65歳以上）",
        "col": "aging_rate",
        "color_fn": rate_color,
        "show": True,
        "legend": [("#0040ff","低（若い地域）"), ("#7f4080","中"), ("#ff4000","高（高齢化）")],
        "label": "高齢化率",
    },
    {
        "name": "超高齢率（75歳以上）",
        "col": "rate_75over",
        "color_fn": rate_color,
        "show": False,
        "legend": [("#0040ff","低"), ("#7f4080","中"), ("#ff4000","高")],
        "label": "75歳以上率",
    },
    {
        "name": "若年層比率（15〜39歳）",
        "col": "rate_15_39",
        "color_fn": green_color,
        "show": False,
        "legend": [("#ffffff","低"), ("#208020","高（若者集積）")],
        "label": "15〜39歳率",
    },
    {
        "name": "子育て世代比率（25〜44歳）",
        "col": "rate_25_44",
        "color_fn": green_color,
        "show": False,
        "legend": [("#ffffff","低"), ("#208020","高（子育て集積）")],
        "label": "25〜44歳率",
    },
    {
        "name": "年少人口比率（0〜14歳）",
        "col": "rate_0_14",
        "color_fn": green_color,
        "show": False,
        "legend": [("#ffffff","低"), ("#208020","高（子ども多い）")],
        "label": "0〜14歳率",
    },
    {
        "name": "生産年齢比率（15〜64歳）",
        "col": "rate_15_64",
        "color_fn": green_color,
        "show": False,
        "legend": [("#ffffff","低"), ("#208020","高（働き盛り）")],
        "label": "15〜64歳率",
    },
]


def main():
    conn = sqlite3.connect(DB_PATH)

    # 必要な列を動的に取得
    rate_cols = [l["col"] for l in LAYERS]
    cols_sql = ", ".join(["mesh_code", "pop_total"] + rate_cols)
    # 存在しない列は NULL として補完
    table_cols = [r[1] for r in conn.execute("PRAGMA table_info(mesh_population)").fetchall()]
    select_parts = ["mesh_code", "pop_total"] + [
        c if c in table_cols else f"NULL as {c}" for c in rate_cols
    ]
    rows = conn.execute(f"""
        SELECT {', '.join(select_parts)}
        FROM mesh_population WHERE pop_total > 0
    """).fetchall()
    print(f"人口ありメッシュ: {len(rows):,} 件")

    pharmacies = conn.execute("""
        SELECT lat, lon, name, zaitaku_flag, iryo_ken, pharmacy_type, ds_only
        FROM pharmacies
        WHERE lat IS NOT NULL AND lon IS NOT NULL
    """).fetchall()
    print(f"薬局（全種別）: {len(pharmacies):,} 件")

    # 中学校区ポリゴン
    districts = conn.execute("""
        SELECT school_name, city_name, geometry_json
        FROM school_districts
    """).fetchall()
    print(f"中学校区: {len(districts)} 件")

    # 市区町村境界
    cities = conn.execute("""
        SELECT city_name, iryo_ken, geometry_json
        FROM city_boundaries
    """).fetchall()
    print(f"市区町村: {len(cities)} 件")

    # 二次医療圏境界
    iryo_kens = conn.execute("""
        SELECT iryo_ken, geometry_json
        FROM iryo_ken_boundaries
    """).fetchall()
    print(f"二次医療圏: {len(iryo_kens)} 件")

    conn.close()

    m = folium.Map(location=[35.6, 140.1], zoom_start=9, tiles="CartoDB positron")

    # 薬局を常に最前面に表示するカスタムPane（z-index 650 > overlayPane 400）
    pane_js = folium.Element("""
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(function() {
            var mapObj = Object.values(window).find(
                function(v){ return v && v._leaflet_id && v.createPane; }
            );
            if (!mapObj) return;
            var p = mapObj.createPane('pharmacyPane');
            p.style.zIndex = 650;
            // レイヤー追加・削除のたびに薬局レイヤーを前面へ
            mapObj.on('overlayadd overlayremove', function() {
                mapObj.eachLayer(function(layer) {
                    if (layer._isPharmacyGroup && layer.bringToFront) {
                        layer.bringToFront();
                    }
                });
            });
        }, 800);
    });
    </script>
    """)
    m.get_root().html.add_child(pane_js)

    # ── メッシュレイヤ（各年齢グループ） ─────────────────────
    for layer in LAYERS:
        col_idx = 2 + rate_cols.index(layer["col"])
        group = folium.FeatureGroup(name=layer["name"], show=layer["show"])
        for row in rows:
            mesh_code = row[0]
            pop_total = row[1]
            rate = row[col_idx]
            try:
                lat_min, lon_min, lat_max, lon_max = mesh_to_bounds(str(mesh_code))
            except Exception:
                continue
            color = layer["color_fn"](rate)
            rate_str = f"{rate}%" if rate is not None else "－"
            popup_html = (
                f"<b>{layer['label']}</b>: {rate_str}<br>"
                f"総人口: {int(pop_total or 0):,}人"
            )
            folium.Rectangle(
                bounds=[[lat_min, lon_min], [lat_max, lon_max]],
                color=None, fill=True,
                fill_color=color, fill_opacity=0.65,
                tooltip=f"{layer['label']}: {rate_str}",
                popup=folium.Popup(popup_html, max_width=180),
            ).add_to(group)
        group.add_to(m)

    # ── 市区町村境界レイヤ ────────────────────────────────
    city_group = folium.FeatureGroup(name="市区町村境界", show=False)
    for city_name, iryo_ken, geom_json in cities:
        try:
            geom = json.loads(geom_json)
        except Exception:
            continue
        folium.GeoJson(
            {"type": "Feature", "geometry": geom, "properties": {}},
            style_function=lambda x: {
                "color": "#555555", "weight": 1.2,
                "fillColor": "transparent", "fillOpacity": 0,
            },
            tooltip=f"{city_name}（{iryo_ken}圏域）"
        ).add_to(city_group)
    city_group.add_to(m)

    # ── 二次医療圏境界レイヤ ──────────────────────────────
    iryo_ken_group = folium.FeatureGroup(name="二次医療圏境界", show=True)
    for iryo_ken, geom_json in iryo_kens:
        try:
            geom = json.loads(geom_json)
        except Exception:
            continue
        folium.GeoJson(
            {"type": "Feature", "geometry": geom, "properties": {}},
            style_function=lambda x: {
                "color": "#cc0033", "weight": 2.5,
                "fillColor": "transparent", "fillOpacity": 0,
            },
            tooltip=f"{iryo_ken}医療圏"
        ).add_to(iryo_ken_group)
    iryo_ken_group.add_to(m)

    # ── 中学校区レイヤ ────────────────────────────────────
    district_group = folium.FeatureGroup(name="中学校区（地域連携薬局設置目標）", show=False)
    for school_name, city_name, geom_json in districts:
        try:
            geom = json.loads(geom_json)
        except Exception:
            continue
        folium.GeoJson(
            {"type": "Feature", "geometry": geom, "properties": {}},
            style_function=lambda x: {
                "color": "#e67e00", "weight": 1.5,
                "fillColor": "#f5a623", "fillOpacity": 0.08,
            },
            tooltip=f"{city_name} / {school_name}"
        ).add_to(district_group)
    district_group.add_to(m)

    # ── 薬局レイヤ（3種別） ───────────────────────────────
    # 独立系（調剤あり）
    grp_indep = folium.FeatureGroup(name="独立系薬局", show=True)
    # チェーン薬局（DS機能含む・調剤あり）
    grp_chain = folium.FeatureGroup(name="チェーン薬局（DS機能含む）", show=True)
    # DS機能のみ（調剤なし）
    grp_ds    = folium.FeatureGroup(name="DS機能のみ（調剤なし）", show=False)

    for lat, lon, name, zaitaku, iryo_ken, ptype, ds_only in pharmacies:
        zaitaku_label = "在宅対応あり" if zaitaku else "在宅対応なし"
        tip = f"{name}　{zaitaku_label}（{iryo_ken}圏域）"
        opts = {"pane": "pharmacyPane"}

        if ds_only == 1:
            folium.CircleMarker(
                location=[lat, lon], radius=3,
                color="#f0a500", fill=True, fill_opacity=0.7,
                tooltip=tip, **opts
            ).add_to(grp_ds)
        elif ptype == "独立":
            color = "#1a6fdb" if zaitaku else "#7fb3f5"
            folium.CircleMarker(
                location=[lat, lon], radius=4,
                color=color, fill=True, fill_opacity=0.9,
                tooltip=tip, **opts
            ).add_to(grp_indep)
        else:
            color = "#22a85a" if zaitaku else "#88cca4"
            folium.CircleMarker(
                location=[lat, lon], radius=3,
                color=color, fill=True, fill_opacity=0.9,
                tooltip=tip, **opts
            ).add_to(grp_chain)

    grp_indep.add_to(m)
    grp_chain.add_to(m)
    grp_ds.add_to(m)

    # 凡例（選択中レイヤの説明）
    legend_html = """
    <div style="position:fixed;bottom:40px;left:40px;z-index:1000;
                background:white;padding:14px 18px;border-radius:8px;
                box-shadow:2px 2px 8px rgba(0,0,0,0.25);font-size:13px;line-height:1.8;">
      <b>🗾 地図の見かた</b><br>
      メッシュの色 = 各レイヤの人口比率<br>
      右上のレイヤボタンで切替<br>
      <br>
      <b>独立系薬局</b><br>
      <span style="color:#1a6fdb;">●</span> 在宅対応あり<br>
      <span style="color:#7fb3f5;">●</span> 在宅対応なし<br>
      <b>チェーン薬局（DS機能含む）</b><br>
      <span style="color:#22a85a;">●</span> 在宅対応あり<br>
      <span style="color:#88cca4;">●</span> 在宅対応なし<br>
      <b>DS機能のみ</b><br>
      <span style="color:#f0a500;">●</span> 調剤なし<br>
      <br>
      <span style="font-size:11px;color:#888;">
      出典: e-Stat 令和2年国勢調査 500mメッシュ<br>
      + 千葉県薬局機能情報 2025年12月<br>
      + 国土数値情報 中学校区 2021年度
      </span>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    folium.LayerControl(collapsed=False).add_to(m)

    OUT.parent.mkdir(exist_ok=True)
    m.save(str(OUT))
    print(f"[OK] 地図を保存: {OUT}")


if __name__ == "__main__":
    main()

"""
千葉県 二次医療圏 色分けマップ生成スクリプト

【初回のみ必要な準備】
国土数値情報 行政区域データ（千葉県）をダウンロード：
  https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2024.html
  → 「千葉県」の GeoJSON をダウンロード（N03-20240101_12_GML.zip）
  → 解凍して N03-20240101_12.geojson を chiba_pdf_db/ に置く

【出力】
  - iryo_ken_map.html  : インタラクティブマップ（ブラウザで開ける）
  - iryo_ken_map.png   : 静的画像（記事挿入用）← matplotlib必要
"""

import sqlite3
import json
from pathlib import Path

import geopandas as gpd
import folium
import pandas as pd

BASE_DIR = Path(r"C:\Users\jumpd\chiba_pdf_db")
DB_PATH = BASE_DIR / "chiba_iryo.db"
GEOJSON_PATH = BASE_DIR / "N03-20240101_12.geojson"
OUTPUT_DIR = Path(r"C:\Users\jumpd\Obsidian_Main\CrossHealth_company\product")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 医療圏ごとの色（9圏域）
IRYO_KEN_COLORS = {
    "千葉":       "#4e79a7",   # 青
    "東葛南部":   "#f28e2b",   # オレンジ
    "東葛北部":   "#e15759",   # 赤
    "印旛":       "#76b7b2",   # ティール
    "香取海匝":   "#59a14f",   # 緑
    "山武長生夷隅": "#edc948", # 黄
    "安房":       "#b07aa1",   # 紫
    "君津":       "#ff9da7",   # ピンク
    "市原":       "#9c755f",   # ブラウン
}


def load_city_iryo_ken():
    """DBから city_code → iryo_ken のマッピングを取得"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT city_code, iryo_ken
        FROM pharmacies
        WHERE city_code IS NOT NULL AND iryo_ken IS NOT NULL
    """)
    rows = cur.fetchall()
    conn.close()
    # city_codeは3桁 → 千葉県コード12を付けて5桁に（例: 101 → 12101）
    return {f"12{str(code).zfill(3)}": ken for code, ken in rows}


def load_pharmacy_stats():
    """圏域別の薬局統計を取得"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT iryo_ken,
            COUNT(*) as total,
            SUM(CASE WHEN ds_only=0 THEN 1 ELSE 0 END) as dispensing,
            SUM(CASE WHEN zaitaku_flag=1 AND ds_only=0 THEN 1 ELSE 0 END) as zaitaku,
            ROUND(100.0*SUM(CASE WHEN zaitaku_flag=1 AND ds_only=0 THEN 1 ELSE 0 END)
                  / NULLIF(SUM(CASE WHEN ds_only=0 THEN 1 ELSE 0 END), 0), 1) as zaitaku_rate
        FROM pharmacies
        GROUP BY iryo_ken
    """)
    rows = cur.fetchall()
    conn.close()
    return {row[0]: {"total": row[1], "dispensing": row[2],
                     "zaitaku": row[3], "zaitaku_rate": row[4]} for row in rows}


def make_iryo_ken_map():
    if not GEOJSON_PATH.exists():
        print(f"エラー: {GEOJSON_PATH} が見つかりません。")
        print("【ダウンロード手順】")
        print("1. https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2024.html を開く")
        print("2. 「千葉県」の行の GeoJSON をダウンロード")
        print(f"3. 解凍して N03-20240101_12.geojson を {BASE_DIR} に置く")
        return

    print("GeoJSON 読み込み中...")
    gdf = gpd.read_file(GEOJSON_PATH)
    print(f"  読み込み完了: {len(gdf)} レコード")
    print(f"  カラム: {list(gdf.columns)}")

    # 市区町村コードのカラム名を特定（N03_007 または CITY_CODE 等）
    code_col = None
    for col in ["N03_007", "CITY_CODE", "N03_006"]:
        if col in gdf.columns:
            code_col = col
            break
    if code_col is None:
        print(f"市区町村コードのカラムが見つかりません。カラム一覧: {list(gdf.columns)}")
        return

    # city_code → iryo_ken マッピングを付与
    city_iryo_ken = load_city_iryo_ken()
    gdf["iryo_ken"] = gdf[code_col].map(city_iryo_ken)

    # 医療圏単位で市区町村ポリゴンを合体（dissolve）
    gdf_iryo = gdf[gdf["iryo_ken"].notna()].dissolve(by="iryo_ken", as_index=False)
    gdf_iryo = gdf_iryo.to_crs(epsg=4326)  # 座標系をWGS84に統一

    # 薬局統計を結合
    stats = load_pharmacy_stats()
    gdf_iryo["dispensing"] = gdf_iryo["iryo_ken"].map(lambda k: stats.get(k, {}).get("dispensing", 0))
    gdf_iryo["zaitaku_rate"] = gdf_iryo["iryo_ken"].map(lambda k: stats.get(k, {}).get("zaitaku_rate", 0))
    gdf_iryo["total"] = gdf_iryo["iryo_ken"].map(lambda k: stats.get(k, {}).get("total", 0))

    print(f"医療圏数: {len(gdf_iryo)}")
    print(gdf_iryo[["iryo_ken", "dispensing", "zaitaku_rate"]].to_string(index=False))

    # --- folium インタラクティブマップ ---
    m = folium.Map(
        location=[35.5, 140.1],
        zoom_start=8,
        tiles="CartoDB positron"
    )

    for _, row in gdf_iryo.iterrows():
        ken = row["iryo_ken"]
        color = IRYO_KEN_COLORS.get(ken, "#aaaaaa")
        geo_json = row["geometry"].__geo_interface__

        popup_html = f"""
        <div style='font-family:sans-serif;min-width:180px;font-size:13px'>
            <b style='font-size:15px'>{ken}医療圏</b><br>
            <hr style='margin:4px 0'>
            調剤薬局: <b>{row['dispensing']}件</b><br>
            在宅対応率: <b>{row['zaitaku_rate']}%</b><br>
            <span style='color:gray;font-size:11px'>（DS専用含む総数: {row['total']}件）</span>
        </div>
        """

        folium.GeoJson(
            data={"type": "Feature", "geometry": geo_json},
            style_function=lambda _, c=color: {
                "fillColor": c,
                "color": "white",
                "weight": 2,
                "fillOpacity": 0.65,
            },
            tooltip=f"{ken}医療圏",
            popup=folium.Popup(popup_html, max_width=250),
        ).add_to(m)

    # 凡例
    legend_items = "".join([
        f"<div style='margin:3px 0'>"
        f"<span style='display:inline-block;width:14px;height:14px;background:{color};"
        f"border-radius:2px;margin-right:6px;vertical-align:middle'></span>"
        f"{ken}医療圏</div>"
        for ken, color in IRYO_KEN_COLORS.items()
    ])
    legend_html = f"""
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:white;padding:12px 16px;border-radius:8px;
                box-shadow:0 2px 8px rgba(0,0,0,0.2);font-family:sans-serif;font-size:12px;">
        <b style='font-size:13px'>千葉県 二次医療圏</b>
        <hr style='margin:6px 0'>
        {legend_items}
        <hr style='margin:6px 0'>
        <span style='color:gray;font-size:10px'>クリックで薬局データを表示</span>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    out_html = OUTPUT_DIR / "iryo_ken_map.html"
    m.save(str(out_html))
    print(f"\nHTMLマップ保存: {out_html}")

    # --- 静的PNG（matplotlibがあれば） ---
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import matplotlib.font_manager as fm

        # Windows日本語フォントを自動検出
        jp_font = None
        for fname in ["Yu Gothic", "Meiryo", "MS Gothic", "Hiragino Sans"]:
            fonts = fm.findSystemFonts()
            matched = [f for f in fonts if fname.lower().replace(" ", "") in f.lower().replace(" ", "").replace("-", "")]
            if matched:
                jp_font = fm.FontProperties(fname=matched[0])
                break
        if jp_font is None:
            # フォールバック：システムフォント一覧から日本語対応を探す
            for f in fm.findSystemFonts():
                if any(k in f for k in ["yugoth", "meiryo", "msgoth", "msmincho"]):
                    jp_font = fm.FontProperties(fname=f)
                    break
        font_kwargs = {"fontproperties": jp_font} if jp_font else {"fontsize": 8}

        fig, ax = plt.subplots(1, 1, figsize=(10, 12))
        for _, row in gdf_iryo.iterrows():
            ken = row["iryo_ken"]
            color = IRYO_KEN_COLORS.get(ken, "#aaaaaa")
            gdf_iryo[gdf_iryo["iryo_ken"] == ken].plot(
                ax=ax, color=color, edgecolor="white", linewidth=1.5
            )
            centroid = row["geometry"].centroid
            ax.annotate(
                ken,
                xy=(centroid.x, centroid.y),
                ha="center", va="center",
                fontsize=8,
                color="white",
                fontweight="bold",
                **({} if not jp_font else {"fontproperties": jp_font})
            )

        patches = [mpatches.Patch(color=c, label=k) for k, c in IRYO_KEN_COLORS.items()]
        legend_kwargs = {"prop": jp_font} if jp_font else {"fontsize": 9}
        ax.legend(handles=patches, loc="lower left", framealpha=0.9, **legend_kwargs)
        title_kwargs = {"fontproperties": jp_font} if jp_font else {"fontsize": 14}
        ax.set_title("千葉県 二次医療圏", pad=10, **title_kwargs)
        ax.axis("off")

        out_png = OUTPUT_DIR / "iryo_ken_map.png"
        plt.tight_layout()
        plt.savefig(str(out_png), dpi=150, bbox_inches="tight")
        plt.close()
        print(f"PNG保存: {out_png}")
    except Exception as e:
        print(f"PNG生成スキップ（matplotlib関連エラー）: {e}")


if __name__ == "__main__":
    make_iryo_ken_map()

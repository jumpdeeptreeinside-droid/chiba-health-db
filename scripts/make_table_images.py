# 記事中の表をnote貼り付け用PNG画像に変換するスクリプト
# 使い方:
#   python make_table_images.py          # 全テーブルを生成
#   python make_table_images.py vol01    # Vol.01のテーブルのみ
# 出力先: communications/tables/

import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
import pandas as pd
from pathlib import Path
import sys

OUTPUT_DIR = Path("C:/Users/jumpd/Obsidian_Main/CrossHealth_company/communications/tables")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 游ゴシック（日本語フォント）
FONT_PATH = "C:/Windows/Fonts/YuGothM.ttc"
FONT_BOLD_PATH = "C:/Windows/Fonts/YuGothB.ttc"
fp = fm.FontProperties(fname=FONT_PATH)
fp_bold = fm.FontProperties(fname=FONT_BOLD_PATH)

# カラーパレット
COLOR_HEADER = "#2c3e50"
COLOR_ROW_ODD = "#f8f9fa"
COLOR_ROW_EVEN = "#ffffff"
COLOR_ACCENT = "#e74c3c"  # 最悪値のハイライト
COLOR_GOOD = "#27ae60"    # 最良値のハイライト
COLOR_BORDER = "#dee2e6"


def save_table(df, title, filename, col_widths=None, highlight_rows=None,
               highlight_cols=None, note=None, figsize=None):
    """
    DataFrameをきれいなPNGテーブルとして保存する汎用関数

    highlight_rows: {行インデックス: 背景色} の dict
    highlight_cols: {列名: 文字色} の dict（数値列のみ対応）
    note: 表の下に小さく表示する注釈文字列
    """
    n_rows, n_cols = df.shape
    note_extra = 0.6 if note else 0.0
    if figsize is None:
        figsize = (max(8, n_cols * 2.2), max(2, n_rows * 0.55) + 1.2 + note_extra)

    fig, ax = plt.subplots(figsize=figsize)
    ax.axis("off")

    # タイトル
    ax.text(0.5, 0.98, title, transform=ax.transAxes,
            ha="center", va="top", fontsize=13, fontweight="bold",
            fontproperties=fp_bold, color=COLOR_HEADER)

    # テーブル描画
    col_w = col_widths or [1.0 / n_cols] * n_cols
    table = ax.table(
        cellText=df.values,
        colLabels=df.columns,
        cellLoc="center",
        loc="center",
        colWidths=col_w,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)

    # スタイル設定
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(COLOR_BORDER)
        cell.set_linewidth(0.5)

        if row == 0:
            # ヘッダー行
            cell.set_facecolor(COLOR_HEADER)
            cell.get_text().set_color("white")
            cell.get_text().set_fontproperties(fp_bold)
            cell.get_text().set_fontsize(10)
            cell.set_height(0.12)
        else:
            # データ行
            data_row = row - 1
            bg = COLOR_ROW_ODD if data_row % 2 == 0 else COLOR_ROW_EVEN
            if highlight_rows and data_row in highlight_rows:
                bg = highlight_rows[data_row]
            cell.set_facecolor(bg)
            cell.get_text().set_fontproperties(fp)
            cell.get_text().set_fontsize(10)
            cell.set_height(0.10)

            # 列ごとの文字色
            if highlight_cols and col < len(df.columns):
                col_name = df.columns[col]
                if col_name in highlight_cols:
                    cell.get_text().set_color(highlight_cols[col_name])

    # 注釈
    if note:
        ax.text(0.5, 0.01, note, transform=ax.transAxes,
                ha="center", va="bottom", fontsize=7.5,
                fontproperties=fp, color="gray", style="italic",
                wrap=True)

    out_path = OUTPUT_DIR / filename
    plt.tight_layout(pad=0.5)
    plt.savefig(str(out_path), dpi=150, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()
    print(f"保存: {out_path}")


# ============================================================
# Vol.01 テーブル定義
# ============================================================

def make_vol01_tables():

    # 0a. 計画の全体像・4本柱
    df0a = pd.DataFrame([
        ["① 質の高い保健医療提供体制の構築", "急性期から在宅まで「循環型」で医療をつなぐ"],
        ["② 総合的な健康づくりの推進",    "予防・生活習慣改善・がん・自殺対策"],
        ["③ 保健・医療・福祉の連携確保",   "母子・高齢者・障害者への一体的なサービス"],
        ["④ 安全と生活を守る環境づくり",   "食品・医薬品の安全、健康危機管理"],
    ], columns=["柱", "内容"])

    save_table(
        df0a,
        title="千葉県保健医療計画 施策の4本柱",
        filename="vol01_table0a_4pillars.png",
        col_widths=[0.40, 0.60],
        note="出典：千葉県保健医療計画（概要版）p.1〜2",
    )

    # 0b. 千葉県医療資源の現状（全国比較）
    df0b = pd.DataFrame([
        ["医師数（人口10万対）",   "205.8",  "—"],
        ["全国順位（医師偏在）",   "38位",   "（47都道府県中）"],
        ["薬剤師数（人口10万対）", "235.9",  "255.2"],
        ["看護職員数（人口10万対）", "972.6", "1,315.2"],
    ], columns=["指標", "千葉県", "全国"])

    save_table(
        df0b,
        title="千葉県の医療資源：全国との比較",
        filename="vol01_table0b_iryo_shigen.png",
        col_widths=[0.45, 0.28, 0.27],
        highlight_rows={1: "#fdecea", 2: "#fdecea"},
        note="出典：千葉県保健医療計画（概要版）p.3、p.13、p.14",
    )

    # 1. 外来医師偏在指標（9圏域）
    df1 = pd.DataFrame([
        ["千葉",         "103.0", "150位"],
        ["東葛南部",     "92.3",  "223位"],
        ["東葛北部",     "90.0",  "233位"],
        ["山武長生夷隅", "85.9",  "255位"],
        ["君津",         "83.6",  "268位"],
        ["安房",         "77.8",  "291位"],
        ["香取海匝",     "77.9",  "290位"],
        ["印旛",         "77.5",  "294位"],
        ["市原",         "69.4",  "318位 ★最低"],
    ], columns=["圏域", "外来医師偏在指標", "全国順位（330圏域中）"])

    save_table(
        df1,
        title="外来医師偏在指標（千葉県 9医療圏）",
        filename="vol01_table1_ishi_henzan.png",
        col_widths=[0.35, 0.32, 0.33],
        highlight_rows={8: "#fdecea"},  # 市原（最低）を薄赤
        note="出典：千葉県保健医療計画（概要版）p.12 ／ 全国平均112.2、千葉県全体88.6（47都道府県中38位）",
    )

    # 2. 薬局在宅対応率（9圏域）
    df2 = pd.DataFrame([
        ["東葛北部",     "403",  "372",  "92.3% ★最高"],
        ["千葉",         "454",  "418",  "92.1%"],
        ["市原",         "108",  "99",   "91.7%"],
        ["山武長生夷隅", "207",  "187",  "90.3%"],
        ["東葛南部",     "854",  "769",  "90.0%"],
        ["君津",         "159",  "140",  "88.1%"],
        ["香取海匝",     "135",  "118",  "87.4%"],
        ["印旛",         "249",  "213",  "85.5%"],
        ["安房",         "64",   "53",   "82.8% ★最低"],
    ], columns=["圏域", "調剤薬局数", "在宅対応薬局数", "在宅対応率"])

    save_table(
        df2,
        title="圏域別 薬局在宅対応率（千葉県）",
        filename="vol01_table2_zaitaku_rate.png",
        col_widths=[0.30, 0.22, 0.25, 0.23],
        highlight_rows={0: "#eafaf1", 8: "#fdecea"},
        note="出典：厚労省「薬局機能情報」オープンデータ（2025年12月）/ 関東信越厚生局 施設基準届出 r0803 ／ CrossHealth独自集計",
    )

    # 3. 必要病床数と現状のギャップ（回復期）
    df3 = pd.DataFrame([
        ["千葉",     "2,520", "1,204", "▲1,316"],
        ["東葛南部", "4,072", "1,904", "▲2,168"],
        ["東葛北部", "3,647", "1,226", "▲2,421"],
        ["印旛",     "1,625", "634",   "▲991"],
    ], columns=["圏域", "回復期 必要病床数", "病床機能報告値（現状）", "差（不足）"])

    save_table(
        df3,
        title="回復期病床の必要量と現状のギャップ（主要4圏域）",
        filename="vol01_table3_kaifukugo.png",
        col_widths=[0.25, 0.27, 0.28, 0.20],
        note="出典：千葉県保健医療計画（概要版）p.5 ／ 全圏域で回復期病床が大幅不足",
    )

    # 4. まとめ
    df4 = pd.DataFrame([
        ["① 千葉県全体",   "医師偏在指標38位・医療資源が全国平均以下"],
        ["② 圏域格差",     "市原（外来医師318位）〜千葉（150位）の大きな格差"],
        ["③ 回復期不足",   "全圏域で回復期病床が大幅不足"],
        ["④ 在宅希望増",   "「在宅で療養したい」36%に上昇（前回比＋3.6pt）"],
        ["⑤ 薬局データ",   "安房圏域：在宅対応率82.8%（最低）× 医師不足が重なる"],
    ], columns=["発見", "内容"])

    save_table(
        df4,
        title="Vol.01 まとめ：5つの発見",
        filename="vol01_table4_summary.png",
        col_widths=[0.22, 0.78],
        highlight_rows={4: "#fef9e7"},
        note="出典：千葉県保健医療計画（概要版）/ CrossHealth独自集計",
    )

    print("\nVol.01 テーブル画像 生成完了")
    print(f"保存先: {OUTPUT_DIR}")


# ============================================================
# Vol.02 テーブル定義（安房圏域）
# ============================================================

def make_vol02_tables():

    # 1. 安房圏域 市区町村別 薬局データ
    df1 = pd.DataFrame([
        ["館山市",   "30", "25", "83.3%"],
        ["南房総市", "16", "11", "68.8% ★最低"],
        ["鴨川市",   "15", "14", "93.3%"],
        ["鋸南町",   "3",  "3",  "100.0%"],
        ["安房計",   "64", "53", "82.8%（県内最低）"],
    ], columns=["市区町村", "調剤薬局数", "在宅対応薬局", "在宅対応率"])

    save_table(
        df1,
        title="安房圏域 市区町村別 薬局在宅対応率",
        filename="vol02_table1_awa_pharmacy.png",
        col_widths=[0.28, 0.24, 0.24, 0.24],
        highlight_rows={1: "#fdecea", 4: "#fef9e7"},
        note="出典：CrossHealth独自集計（厚労省薬局機能情報 2025年12月／関東信越厚生局 施設基準届出 r0803）",
    )

    # 2. 安房圏域 必要病床数と現状のギャップ（2025年）
    df2 = pd.DataFrame([
        ["高度急性期", "308",   "—",     "—"],
        ["急性期",     "602",   "—",     "—"],
        ["回復期",     "358",   "124",   "▲234"],
        ["慢性期",     "373",   "—",     "—"],
        ["合計",       "1,641", "1,208", "▲433"],
    ], columns=["病床機能", "必要病床数（2025年）", "病床機能報告値", "差（不足）"])

    save_table(
        df2,
        title="安房圏域 必要病床数と現状のギャップ",
        filename="vol02_table2_awa_beds.png",
        col_widths=[0.22, 0.30, 0.26, 0.22],
        highlight_rows={2: "#fdecea"},
        note="出典：千葉県保健医療計画（chiikiiryoukousou.pdf p.11-14）／回復期の不足が顕著",
    )

    # 3. 安房圏域 人口推移予測
    df3 = pd.DataFrame([
        ["2020年", "120,000", "—"],
        ["2025年", "111,000", "▲7.5%"],
        ["2030年", "103,000", "▲14.2%"],
        ["2040年",  "88,000", "▲26.7%"],
        ["2050年",  "75,000", "▲37.5% ★"],
    ], columns=["年", "推計人口", "2020年比"])

    save_table(
        df3,
        title="安房圏域 人口推移予測（2020〜2050年）",
        filename="vol02_table3_awa_population.png",
        col_widths=[0.25, 0.38, 0.37],
        highlight_rows={4: "#fdecea"},
        note="出典：千葉県保健医療計画（4iryouken.pdf p.27）／2050年までに約4割減の見通し",
    )

    # 4. まとめ
    df4 = pd.DataFrame([
        ["① 医師偏在",   "外来医師偏在指標77.8・全国291位（千葉県内ワースト2位）"],
        ["② 薬局格差",   "在宅対応率82.8%（県内最低）。南房総市は68.8%と特に低い"],
        ["③ 人口危機",   "2050年までに人口が37.5%減少する見通し"],
        ["④ 病床の逆説", "病院数・病床数は県内最多水準だが、回復期が慢性的に不足"],
        ["⑤ 複合課題",   "医師不足×薬局弱体×人口減少が同時進行する「三重苦」"],
    ], columns=["発見", "内容"])

    save_table(
        df4,
        title="Vol.02 まとめ：安房圏域の5つの課題",
        filename="vol02_table4_summary.png",
        col_widths=[0.20, 0.80],
        highlight_rows={4: "#fef9e7"},
        note="出典：千葉県保健医療計画（概要版・各圏域編）／CrossHealth独自集計",
    )

    print("\nVol.02 テーブル画像 生成完了")
    print(f"保存先: {OUTPUT_DIR}")


# ============================================================
# エントリーポイント
# ============================================================

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"

    if target in ("vol01", "all"):
        make_vol01_tables()

    # 今後 vol02, vol03 ... を追加していく
    # if target in ("vol02", "all"):
    #     make_vol02_tables()

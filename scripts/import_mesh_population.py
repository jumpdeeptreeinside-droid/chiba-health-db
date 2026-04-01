"""
e-Stat 500mメッシュ人口データを SQLite にインポートするスクリプト

対象ファイル:
  tblT001141H12.zip ... 人口及び世帯（総人口・高齢者人口など）
  tblT001192H12.zip ... 5歳階級別人口

出力テーブル: mesh_population（chiba_iryo.db）

実行例:
  python scripts/import_mesh_population.py \
    --t001141 "path/to/tblT001141H12.zip" \
    --t001192 "path/to/tblT001192H12.zip"
"""

import argparse
import sqlite3
import zipfile
import io
from pathlib import Path

import pandas as pd

ROOT    = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "chiba_iryo.db"


def read_estat_csv(zip_path: str) -> pd.DataFrame:
    """e-Stat CSVをzipから読み込む（Shift-JIS、2行ヘッダ）"""
    with zipfile.ZipFile(zip_path) as z:
        name = z.namelist()[0]
        with z.open(name) as f:
            raw = f.read().decode("cp932", errors="replace")
    # 1行目=列コード、2行目=列ラベル（日本語）→1行目だけをヘッダに使う
    df = pd.read_csv(io.StringIO(raw), header=0, skiprows=[1], dtype=str)
    return df


def build_mesh_table(t001141_path: str, t001192_path: str) -> pd.DataFrame:
    """2ファイルから必要な列だけ抽出して結合する"""

    # ── 人口及び世帯（T001141） ──────────────────────────────
    df1 = read_estat_csv(t001141_path)

    # 必要な列を抽出（定義書に基づく列番号）
    # T001141001=総人口 / 002=男 / 003=女
    # T001141019=65歳以上 / 022=75歳以上
    # T001141034=世帯数
    cols1 = {
        "KEY_CODE":     "mesh_code",
        "T001141001":   "pop_total",
        "T001141002":   "pop_male",
        "T001141003":   "pop_female",
        "T001141019":   "pop_65over",
        "T001141022":   "pop_75over",
        "T001141034":   "households",
    }
    # 存在する列だけ抽出
    existing1 = {k: v for k, v in cols1.items() if k in df1.columns}
    df1 = df1[list(existing1.keys())].rename(columns=existing1)

    # ── 5歳階級別人口（T001192） ─────────────────────────────
    # 列の対応（総数のみ、3列おきに並ぶ）:
    #   004=0-4歳 / 007=5-9 / 010=10-14 / 013=15-19 / 016=20-24
    #   019=25-29 / 022=30-34 / 025=35-39 / 028=40-44 / 031=45-49
    #   034=50-54 / 037=55-59 / 040=60-64 / 043=65-69 / 046=70-74
    #   049=75-79 / 052=80-84 / 055=85-89 / 058=90-94 / 061=95歳以上
    #   064=平均年齢 / 065=年齢中央値
    df2 = read_estat_csv(t001192_path)

    age_cols = {
        "KEY_CODE":     "mesh_code",
        "T001192004":   "ag_0_4",
        "T001192007":   "ag_5_9",
        "T001192010":   "ag_10_14",
        "T001192013":   "ag_15_19",
        "T001192016":   "ag_20_24",
        "T001192019":   "ag_25_29",
        "T001192022":   "ag_30_34",
        "T001192025":   "ag_35_39",
        "T001192028":   "ag_40_44",
        "T001192031":   "ag_45_49",
        "T001192034":   "ag_50_54",
        "T001192037":   "ag_55_59",
        "T001192040":   "ag_60_64",
        "T001192043":   "ag_65_69",
        "T001192046":   "ag_70_74",
        "T001192049":   "ag_75_79",
        "T001192052":   "ag_80_84",
        "T001192055":   "ag_85_89",
        "T001192058":   "ag_90_94",
        "T001192061":   "ag_95over",
        "T001192064":   "age_mean",
        "T001192065":   "age_median",
    }
    existing2 = {k: v for k, v in age_cols.items() if k in df2.columns}
    df2 = df2[list(existing2.keys())].rename(columns=existing2)

    # ── 結合 ────────────────────────────────────────────────
    df = pd.merge(df1, df2, on="mesh_code", how="left")

    # 数値変換（"*"=秘匿値 → NaN）
    num_cols = [c for c in df.columns if c != "mesh_code"]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    def safe_sum(df, cols):
        existing = [c for c in cols if c in df.columns]
        return df[existing].sum(axis=1, min_count=1)

    def rate(num, denom):
        return (num / denom.replace(0, float("nan")) * 100).round(1)

    total = df["pop_total"]

    # 主要年齢グループを集計
    df["pop_0_14"]   = safe_sum(df, ["ag_0_4","ag_5_9","ag_10_14"])
    df["pop_15_39"]  = safe_sum(df, ["ag_15_19","ag_20_24","ag_25_29","ag_30_34","ag_35_39"])
    df["pop_25_44"]  = safe_sum(df, ["ag_25_29","ag_30_34","ag_35_39","ag_40_44"])
    df["pop_15_64"]  = safe_sum(df, [f"ag_{a}_{b}" for a,b in
                                     [(15,19),(20,24),(25,29),(30,34),(35,39),
                                      (40,44),(45,49),(50,54),(55,59),(60,64)]])
    df["pop_65_74"]  = safe_sum(df, ["ag_65_69","ag_70_74"])
    df["pop_75over"] = safe_sum(df, ["ag_75_79","ag_80_84","ag_85_89","ag_90_94","ag_95over"])

    # 各グループの人口比率
    df["rate_0_14"]  = rate(df["pop_0_14"],  total)
    df["rate_15_39"] = rate(df["pop_15_39"], total)
    df["rate_25_44"] = rate(df["pop_25_44"], total)
    df["rate_15_64"] = rate(df["pop_15_64"], total)
    df["aging_rate"] = rate(df["pop_65over"], total)   # 65歳以上
    df["rate_75over"]= rate(df["pop_75over"], total)

    # HTKSYORI=1（実データ）のみ残す（=2は集計元メッシュで重複）
    # KEY_CODEの長さで判定（500mメッシュは9桁）
    df = df[df["mesh_code"].str.len() == 9].copy()

    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--t001141", required=True, help="人口及び世帯 ZIPパス")
    parser.add_argument("--t001192", required=True, help="5歳階級別人口 ZIPパス")
    args = parser.parse_args()

    print("[START] 500mメッシュ人口データ インポート")

    df = build_mesh_table(args.t001141, args.t001192)
    print(f"  メッシュ数: {len(df):,} 件")
    print(f"  列: {list(df.columns)}")

    conn = sqlite3.connect(DB_PATH)
    df.to_sql("mesh_population", conn, if_exists="replace", index=False)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mesh_code ON mesh_population(mesh_code)")
    conn.commit()

    # 確認
    count = conn.execute("SELECT COUNT(*) FROM mesh_population").fetchone()[0]
    sample = conn.execute(
        "SELECT mesh_code, pop_total, pop_65over, aging_rate FROM mesh_population "
        "WHERE pop_total > 0 LIMIT 3"
    ).fetchall()
    conn.close()

    print(f"[OK] mesh_population テーブル: {count:,} 件インポート完了")
    print("  サンプル:")
    for row in sample:
        print(f"    メッシュ:{row[0]}  総人口:{row[1]}  65歳以上:{row[2]}  高齢化率:{row[3]}%")


if __name__ == "__main__":
    main()

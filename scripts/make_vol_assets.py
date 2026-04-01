"""
地域医療スポッター アセット一括生成スクリプト

【使い方】
  python make_vol_assets.py vol02          # 表PNG生成
  python make_vol_assets.py vol02 --data   # 表PNG生成 + DBサマリー出力

【新しいVolを追加するとき】
  1. make_table_images.py に make_vol0X_tables() を追記
  2. このファイルの VOL_CONFIG に追記
  3. python make_vol_assets.py vol0X --data で動作確認
"""

import sys
import sqlite3
from pathlib import Path
import pandas as pd

DB_PATH = Path("C:/Users/jumpd/chiba_pdf_db/chiba_iryo.db")

# ============================================================
# Vol番号 → 関数・対象圏域のマッピング
# ここだけ追記していけばOK
# ============================================================
VOL_CONFIG = {
    "vol01": {
        "region": None,   # 全県
        "module": "make_table_images",
        "func":   "make_vol01_tables",
    },
    "vol02": {
        "region": "安房",
        "module": "make_table_images",
        "func":   "make_vol02_tables",
    },
    # "vol03": { "region": "市原", ... },
}


def query_region_stats(iryo_ken: str):
    """指定した医療圏のDBサマリーを出力（記事執筆の下調べ用）"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 圏域全体
    cur.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN ds_only=0 THEN 1 ELSE 0 END) as dispensing,
            SUM(CASE WHEN zaitaku_flag=1 AND ds_only=0 THEN 1 ELSE 0 END) as zaitaku,
            ROUND(100.0 * SUM(CASE WHEN zaitaku_flag=1 AND ds_only=0 THEN 1 ELSE 0 END)
                  / NULLIF(SUM(CASE WHEN ds_only=0 THEN 1 ELSE 0 END), 0), 1) as zaitaku_rate
        FROM pharmacies
        WHERE iryo_ken = ?
    """, (iryo_ken,))
    row = cur.fetchone()

    # 市区町村別
    cur.execute("""
        SELECT city_code,
            COUNT(*) as cnt,
            SUM(CASE WHEN zaitaku_flag=1 AND ds_only=0 THEN 1 ELSE 0 END) as zaitaku,
            ROUND(100.0 * SUM(CASE WHEN zaitaku_flag=1 AND ds_only=0 THEN 1 ELSE 0 END)
                  / NULLIF(COUNT(*), 0), 1) as rate
        FROM pharmacies
        WHERE iryo_ken = ? AND ds_only = 0
        GROUP BY city_code
        ORDER BY cnt DESC
    """, (iryo_ken,))
    cities = cur.fetchall()

    # 県全体との比較
    cur.execute("""
        SELECT
            ROUND(100.0 * SUM(CASE WHEN zaitaku_flag=1 AND ds_only=0 THEN 1 ELSE 0 END)
                  / NULLIF(SUM(CASE WHEN ds_only=0 THEN 1 ELSE 0 END), 0), 1)
        FROM pharmacies
    """)
    pref_rate = cur.fetchone()[0]

    conn.close()

    print(f"\n{'='*55}")
    print(f"  DBサマリー ／ {iryo_ken}医療圏")
    print(f"{'='*55}")
    print(f"  調剤薬局数（DS除く）: {row[1]} 件")
    print(f"  在宅対応薬局数      : {row[2]} 件")
    print(f"  在宅対応率          : {row[3]} %  （県全体 {pref_rate}%）")
    print(f"\n  市区町村別内訳:")
    for code, cnt, zaitaku, rate in cities:
        bar = "★" if rate and rate < 85 else ""
        print(f"    city_code={code:<6} {cnt:>3}件  在宅{rate}% {bar}")
    print(f"{'='*55}\n")
    print("  ↑ この数字をコピーして vol_template.md に貼り付けてください\n")


def run_vol(vol: str, show_data: bool):
    cfg = VOL_CONFIG.get(vol)
    if cfg is None:
        print(f"エラー: {vol} はVOL_CONFIGに未登録です")
        return

    # DBサマリー出力
    if show_data and cfg["region"]:
        query_region_stats(cfg["region"])

    # 表PNG生成
    import importlib
    mod = importlib.import_module(cfg["module"])
    func = getattr(mod, cfg["func"])
    func()


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("使い方: python make_vol_assets.py vol01|vol02 [--data]")
        print("\n登録済みVol:", list(VOL_CONFIG.keys()))
        sys.exit(0)

    vol = args[0]
    show_data = "--data" in args
    run_vol(vol, show_data)

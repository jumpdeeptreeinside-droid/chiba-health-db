"""
SQLite → Parquet エクスポートスクリプト

実行:
  python scripts/export_parquet.py

GitHub Actions の export_parquet.yml から自動実行される。
DB が更新されるたびに Parquet を再生成・コミットする。
"""

import sqlite3
import pandas as pd
from pathlib import Path

ROOT     = Path(__file__).parent.parent
DB_PATH  = ROOT / "data" / "chiba_iryo.db"
DATA_DIR = ROOT / "data"

# エクスポート対象テーブル（pagesテーブルは大量テキストのためスキップ）
TABLES = {
    "pharmacies": "pharmacies.parquet",
    "documents":  "documents.parquet",
}

def export_table(conn: sqlite3.Connection, table: str, out_path: Path) -> None:
    df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    df.to_parquet(out_path, index=False, engine="pyarrow")
    print(f"  {table}: {len(df):,} 行 → {out_path.name}")

def main():
    print(f"DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    for table, filename in TABLES.items():
        export_table(conn, table, DATA_DIR / filename)
    conn.close()
    print("Parquet エクスポート完了")

if __name__ == "__main__":
    main()

"""
千葉県保健医療計画 PDF全文テキストDB構築スクリプト
pdfs/ フォルダの39本を読み込み、SQLite FTS5 に格納する

テーブル構成:
  documents (id, filename, title)
  pages     (id, doc_id, page_num, text)
  pages_fts (FTS5仮想テーブル → pages に JOIN)

実行例:
  python scripts/build_pdf_db.py
  python scripts/build_pdf_db.py --pdf-dir /path/to/pdfs
"""

import argparse
import sqlite3
from pathlib import Path

import pdfplumber

ROOT    = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "chiba_iryo.db"
PDF_DIR = Path(r"C:\Users\jumpd\chiba_pdf_db\pdfs")

# PDF ファイル名 → わかりやすいタイトル
TITLE_MAP = {
    "gaiyou.pdf":              "概要版",
    "kihonhoushin.pdf":        "第1章 基本方針",
    "genjyo-1.pdf":            "第2章 現状（1）",
    "genjyo-2kai.pdf":         "第2章 現状（2改）",
    "genjyo-3kai.pdf":         "第2章 現状（3改）",
    "genjyo-4kai.pdf":         "第2章 現状（4改）",
    "kenkoudukuri.pdf":        "第3章 健康づくり",
    "gan.pdf":                 "第4章 がん対策",
    "nousochu.pdf":            "第4章 脳卒中対策",
    "sinkekkan.pdf":           "第4章 心血管疾患対策",
    "tounyoubyou.pdf":         "第4章 糖尿病対策",
    "seisinsikkan.pdf":        "第4章 精神疾患対策",
    "ninchishou.pdf":          "第4章 認知症対策",
    "kyuukyuuiryou.pdf":       "第5章 救急医療",
    "saigaiji.pdf":            "第5章 災害時医療",
    "sinkoukansensyou.pdf":    "第5章 新興感染症対策",
    "shuusanki.pdf":           "第5章 周産期医療",
    "shouni.pdf":              "第5章 小児医療",
    "gairaiiryou.pdf":         "第5章 外来医療",
    "zaitakuiryou.pdf":        "第5章 在宅医療",
    "kankyodukuri.pdf":        "第6章 環境づくり",
    "ishikakuho.pdf":          "第7章 医師確保計画",
    "jyuryoukoudou.pdf":       "第7章 受療行動調査",
    "kakushusippeitaisaku.pdf":"第7章 各種疾病対策",
    "degitalka.pdf":           "第7章 デジタル化",
    "systemsouron.pdf":        "第7章 システム総論",
    "renkeikakuho.pdf":        "第7章 連携確保",
    "ishiigai.pdf":            "第7章 医師以外の医療従事者確保",
    "hokeniryouken.pdf":       "別冊 地域編（保健医療圏）",
    "4iryouken.pdf":           "別冊 地域編（4疾病医療圏）",
    "5iryouken.pdf":           "別冊 地域編（5事業医療圏）",
    "chiikiiryoukousou.pdf":   "別冊 地域医療構想",
    "kinoubunnka.pdf":         "別冊 機能分化",
    "besatsumokuji.pdf":       "別冊 目次",
    "besatsusanko.pdf":        "別冊 参考資料",
    "bessatsuhyoushi.pdf":     "別冊 表紙",
    "honsatsusankou.pdf":      "本冊 参考資料",
    "mokuji.pdf":              "目次",
    "hyoushi.pdf":             "表紙",
}


def create_tables(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id       INTEGER PRIMARY KEY,
            filename TEXT UNIQUE,
            title    TEXT
        );

        CREATE TABLE IF NOT EXISTS pages (
            id       INTEGER PRIMARY KEY,
            doc_id   INTEGER REFERENCES documents(id),
            page_num INTEGER,
            text     TEXT
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts
        USING fts5(text, content=pages, content_rowid=id);
    """)
    conn.commit()


def index_pdf(conn: sqlite3.Connection, pdf_path: Path) -> int:
    filename = pdf_path.name
    title = TITLE_MAP.get(filename, filename)

    # documents テーブルに upsert
    conn.execute(
        "INSERT OR IGNORE INTO documents (filename, title) VALUES (?, ?)",
        (filename, title)
    )
    doc_id = conn.execute(
        "SELECT id FROM documents WHERE filename=?", (filename,)
    ).fetchone()[0]

    # 既存ページを削除（再インポート対応）
    old_ids = [r[0] for r in conn.execute(
        "SELECT id FROM pages WHERE doc_id=?", (doc_id,)
    ).fetchall()]
    if old_ids:
        conn.execute(
            f"DELETE FROM pages_fts WHERE rowid IN ({','.join('?'*len(old_ids))})",
            old_ids
        )
        conn.execute("DELETE FROM pages WHERE doc_id=?", (doc_id,))

    pages_inserted = 0
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                text = text.strip()
                if not text:
                    continue
                cur = conn.execute(
                    "INSERT INTO pages (doc_id, page_num, text) VALUES (?, ?, ?)",
                    (doc_id, i, text)
                )
                conn.execute(
                    "INSERT INTO pages_fts (rowid, text) VALUES (?, ?)",
                    (cur.lastrowid, text)
                )
                pages_inserted += 1
    except Exception as e:
        print(f"  [WARN] {filename}: {e}")

    return pages_inserted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-dir", default=str(PDF_DIR))
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    print(f"[START] PDF全文インデックス構築: {len(pdfs)}本")

    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)

    total_pages = 0
    for pdf_path in pdfs:
        pages = index_pdf(conn, pdf_path)
        total_pages += pages
        print(f"  {pdf_path.name}: {pages}ページ")
        conn.commit()

    doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    page_count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    conn.close()

    print(f"\n[OK] documents: {doc_count}件, pages: {page_count}ページ")
    print("FTS5インデックス構築完了 → generate_draft.py からPDF引用が可能になりました")


if __name__ == "__main__":
    main()

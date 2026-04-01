import requests
import pdfplumber
import sqlite3
import sys
import time
from pathlib import Path

# --- 設定 ---
BASE_URL = "https://www.pref.chiba.lg.jp/kenfuku/keikaku/kenkoufukushi/documents/"
OUTPUT_DIR = Path(r"C:\Users\jumpd\chiba_pdf_db")
PDF_DIR = OUTPUT_DIR / "pdfs"
DB_PATH = OUTPUT_DIR / "chiba_iryo.db"

PDF_DIR.mkdir(parents=True, exist_ok=True)

PDFS = [
    ("gaiyou.pdf",            "千葉県保健医療計画（概要版）"),
    ("hyoushi.pdf",           "表紙～はじめに"),
    ("mokuji.pdf",            "目次"),
    ("kihonhoushin.pdf",      "改定に当たっての基本方針"),
    ("genjyo-1.pdf",          "現状_第1節_人口"),
    ("genjyo-2kai.pdf",       "現状_第2節_医療資源"),
    ("genjyo-3kai.pdf",       "現状_第3節_受療動向"),
    ("genjyo-4kai.pdf",       "現状_第4節_県民の意識・意向"),
    ("hokeniryouken.pdf",     "保健医療圏と基準病床数"),
    ("chiikiiryoukousou.pdf", "地域医療構想"),
    ("systemsouron.pdf",      "総論"),
    ("gan.pdf",               "疾病_がん"),
    ("nousochu.pdf",          "疾病_脳卒中"),
    ("sinkekkan.pdf",         "疾病_心筋梗塞等の心血管疾患"),
    ("tounyoubyou.pdf",       "疾病_糖尿病"),
    ("seisinsikkan.pdf",      "疾病_精神疾患（認知症を除く）"),
    ("ninchishou.pdf",        "疾病_認知症"),
    ("kyuukyuuiryou.pdf",     "疾病_救急医療"),
    ("saigaiji.pdf",          "疾病_災害時における医療"),
    ("sinkoukansensyou.pdf",  "疾病_新興感染症"),
    ("shuusanki.pdf",         "疾病_周産期医療"),
    ("shouni.pdf",            "疾病_小児医療"),
    ("kinoubunnka.pdf",       "地域医療の機能分化と連携"),
    ("zaitakuiryou.pdf",      "在宅医療の推進"),
    ("gairaiiryou.pdf",       "外来医療に係る医療提供体制の確保"),
    ("jyuryoukoudou.pdf",     "県民の適切な受療行動の促進"),
    ("kakushusippeitaisaku.pdf", "各種疾病対策等の推進"),
    ("ishikakuho.pdf",        "医師の確保"),
    ("ishiigai.pdf",          "医師以外の人材の養成確保"),
    ("degitalka.pdf",         "医療分野のデジタル化"),
    ("kenkoudukuri.pdf",      "総合的な健康づくりの推進等"),
    ("renkeikakuho.pdf",      "保健・医療・福祉の連携確保"),
    ("kankyodukuri.pdf",      "安全と生活を守る環境づくり"),
    ("honsatsusankou.pdf",    "参考"),
    ("bessatsuhyoushi.pdf",   "別冊_表紙"),
    ("besatsumokuji.pdf",     "別冊_目次"),
    ("5iryouken.pdf",         "別冊_第1章〜第5章"),
    ("4iryouken.pdf",         "別冊_第6章〜第9章"),
    ("besatsusanko.pdf",      "別冊_参考"),
]

# --- DB初期化 ---
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.executescript("""
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY,
        filename TEXT,
        title TEXT,
        total_pages INTEGER
    );
    CREATE TABLE IF NOT EXISTS pages (
        id INTEGER PRIMARY KEY,
        doc_id INTEGER,
        page_num INTEGER,
        text TEXT,
        FOREIGN KEY(doc_id) REFERENCES documents(id)
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
        text,
        content='pages',
        content_rowid='id'
    );
""")
conn.commit()

# --- メイン処理 ---
sys.stdout.reconfigure(encoding='utf-8')

total = len(PDFS)
for i, (filename, title) in enumerate(PDFS, 1):
    pdf_path = PDF_DIR / filename
    print(f"[{i:02d}/{total}] {title}", flush=True)

    # ダウンロード（既存ならスキップ）
    if not pdf_path.exists():
        url = BASE_URL + filename
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            pdf_path.write_bytes(r.content)
            print(f"  → ダウンロード完了 ({len(r.content)//1024}KB)", flush=True)
            time.sleep(0.5)  # サーバー負荷軽減
        except Exception as e:
            print(f"  → エラー: {e}", flush=True)
            continue
    else:
        print(f"  → スキップ（既存）", flush=True)

    # テキスト抽出 & DB格納
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            cur.execute(
                "INSERT OR REPLACE INTO documents (filename, title, total_pages) VALUES (?,?,?)",
                (filename, title, total_pages)
            )
            doc_id = cur.lastrowid

            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                cur.execute(
                    "INSERT INTO pages (doc_id, page_num, text) VALUES (?,?,?)",
                    (doc_id, page_num, text)
                )
                page_id = cur.lastrowid
                if text.strip():
                    cur.execute(
                        "INSERT INTO pages_fts (rowid, text) VALUES (?,?)",
                        (page_id, text)
                    )

            conn.commit()
            print(f"  → DB格納完了 ({total_pages}ページ)", flush=True)
    except Exception as e:
        print(f"  → 抽出エラー: {e}", flush=True)

conn.close()
print("\n✅ 完了！DB: chiba_iryo.db")

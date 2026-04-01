import sqlite3
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai

# 設定
BASE_DIR = Path(r"C:\Users\jumpd\chiba_pdf_db")
DB_PATH = BASE_DIR / "chiba_iryo.db"

load_dotenv(BASE_DIR / ".env")
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

sys.stdout.reconfigure(encoding="utf-8")


def get_keywords_via_gemini(question: str) -> list[str]:
    """Geminiに検索キーワードを考えさせる"""
    prompt = f"""以下の質問に対して、「千葉県保健医療計画」という行政文書の中に
実際に出現しそうな検索キーワードを5個以内で答えてください。
漢字・カタカナ・アルファベット（ACP、ICTなど）も含めてよいです。
キーワードのみをカンマ区切りで答えてください。説明は不要です。

質問: {question}"""

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    raw = response.text.strip()
    keywords = [k.strip() for k in raw.replace("、", ",").split(",") if k.strip()]
    return keywords[:5]


def search_db(keywords: list[str], limit: int = 8) -> list[dict]:
    """SQLite FTSで関連ページを検索"""
    if not keywords:
        return []

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    results = {}
    for kw in keywords:
        try:
            cur.execute("""
                SELECT d.title, p.page_num, p.text, p.id
                FROM pages_fts
                JOIN pages p ON pages_fts.rowid = p.id
                JOIN documents d ON p.doc_id = d.id
                WHERE pages_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (kw, limit))
            for row in cur.fetchall():
                pid = row[3]
                if pid not in results:
                    results[pid] = {"title": row[0], "page": row[1], "text": row[2]}
        except Exception:
            continue

    conn.close()
    return list(results.values())[:limit]


def ask(question: str) -> str:
    """キーワード生成 → 検索 → Geminiで回答生成"""
    keywords = get_keywords_via_gemini(question)

    chunks = search_db(keywords)

    if not chunks:
        return f"関連する情報が見つかりませんでした。\n（検索キーワード: {', '.join(keywords)}）"

    context = "\n\n".join([
        f"【{c['title']} p.{c['page']}】\n{c['text'][:600]}"
        for c in chunks
    ])

    prompt = f"""あなたは千葉県の医療政策の専門家アシスタントです。
以下の「千葉県保健医療計画」の抜粋をもとに、質問に答えてください。
抜粋に含まれない情報は「資料には記載がありません」と答えてください。
回答の最後に、参照した資料名とページ番号を列挙してください。

## 資料の抜粋
{context}

## 質問
{question}

## 回答（日本語・簡潔に）"""

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    return response.text


def main():
    print("=" * 50)
    print("千葉県保健医療計画 検索システム")
    print("終了: Ctrl+C または 'q'")
    print("=" * 50)

    while True:
        try:
            question = input("\n質問: ").strip()
            if question.lower() in ("q", "quit", "exit"):
                break
            if not question:
                continue
            print("\n回答中...\n")
            answer = ask(question)
            print(answer)
        except KeyboardInterrupt:
            break

    print("\n終了します。")


if __name__ == "__main__":
    main()

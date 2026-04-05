#!/usr/bin/env python3
"""全国医療計画PDFのEmbeddingインデックスを構築する。

各都道府県DBのpagesテーブルからテキストを収集し、チャンク化、
Gemini Embedding APIでベクトル化してSQLiteに保存する。
"""

from __future__ import annotations

import glob
import json
import os
import sqlite3
import struct
import time
from pathlib import Path
from typing import Optional

import numpy as np
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
EMBED_MODEL = "gemini-embedding-001"
EMBED_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{EMBED_MODEL}:embedContent?key={GEMINI_API_KEY}"
)
RAG_DB_PATH = BASE_DIR / "rag_medical_plans.db"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 50
BATCH_SIZE = 20  # Gemini allows batching — we'll do single for simplicity
SLEEP_SEC = 0.1


# ---------------------------------------------------------------------------
# DB discovery
# ---------------------------------------------------------------------------

def discover_databases() -> list[dict]:
    """Find all prefecture databases with documents/pages tables."""
    home = Path.home()
    candidates = []

    # Chiba
    candidates.append({"path": home / "chiba_pdf_db" / "chiba_iryo.db", "pref": "千葉県"})
    # Osaka
    candidates.append({"path": home / "osaka_pdf_db" / "osaka_iryo.db", "pref": "大阪府"})

    # prefdb_XX_name pattern
    for d in sorted(home.glob("prefdb_*")):
        parts = d.name.split("_", 2)
        if len(parts) >= 3:
            code = parts[1]
            pref_name = parts[2]
            db_file = d / f"{code}_iryo.db"
            if db_file.exists():
                candidates.append({"path": db_file, "pref": pref_name})

    # Filter to those that actually have documents + pages tables
    valid = []
    for c in candidates:
        if not c["path"].exists():
            continue
        try:
            conn = sqlite3.connect(c["path"])
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents'")
            has_docs = cur.fetchone() is not None
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pages'")
            has_pages = cur.fetchone() is not None
            conn.close()
            if has_docs and has_pages:
                valid.append(c)
        except Exception:
            continue

    return valid


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    if not text or not text.strip():
        return []
    text = text.strip()
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


# ---------------------------------------------------------------------------
# Embedding API
# ---------------------------------------------------------------------------

def embed_text(text: str, retries: int = 3) -> list[float] | None:
    """Get embedding vector from Gemini API."""
    payload = {
        "content": {"parts": [{"text": text}]},
        "taskType": "RETRIEVAL_DOCUMENT",
    }
    for attempt in range(retries):
        try:
            resp = requests.post(EMBED_URL, json=payload, timeout=30)
            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data["embedding"]["values"]
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                print(f"  Embedding failed: {e}")
                return None
    return None


def embed_batch(texts: list[str], retries: int = 3) -> list[list[float] | None]:
    """Batch embed using batchEmbedContents endpoint."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{EMBED_MODEL}:batchEmbedContents?key={GEMINI_API_KEY}"
    )
    requests_list = [
        {
            "model": f"models/{EMBED_MODEL}",
            "content": {"parts": [{"text": t}]},
            "taskType": "RETRIEVAL_DOCUMENT",
        }
        for t in texts
    ]
    payload = {"requests": requests_list}

    for attempt in range(retries):
        try:
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            return [e["values"] for e in data["embeddings"]]
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                print(f"  Batch embedding failed: {e}")
                return [None] * len(texts)
    return [None] * len(texts)


def float_list_to_blob(vec: list[float]) -> bytes:
    """Convert float list to binary blob (float32)."""
    return struct.pack(f"{len(vec)}f", *vec)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def init_rag_db(db_path: Path) -> sqlite3.Connection:
    """Create/reset the RAG database."""
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS chunks")
    conn.execute("""
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY,
            prefecture TEXT,
            doc_title TEXT,
            page_num INTEGER,
            chunk_text TEXT,
            embedding BLOB
        )
    """)
    conn.execute("CREATE INDEX idx_chunks_pref ON chunks(prefecture)")
    conn.commit()
    return conn


def collect_pages(db_info: dict) -> list[dict]:
    """Collect all pages from a prefecture DB."""
    conn = sqlite3.connect(db_info["path"])
    cur = conn.cursor()
    cur.execute("""
        SELECT d.title, p.page_num, p.text
        FROM pages p
        JOIN documents d ON p.doc_id = d.id
        WHERE p.text IS NOT NULL AND p.text != ''
    """)
    rows = [{"title": r[0], "page_num": r[1], "text": r[2], "pref": db_info["pref"]}
            for r in cur.fetchall()]
    conn.close()
    return rows


def main():
    print("=" * 60)
    print("全国医療計画 RAG Embedding インデックス構築")
    print("=" * 60)

    # Discover DBs
    dbs = discover_databases()
    print(f"\n{len(dbs)} 都道府県DBを検出:")
    for db in dbs:
        print(f"  - {db['pref']}: {db['path']}")

    # Collect all pages
    print("\nページ収集中...")
    all_pages = []
    for db in dbs:
        pages = collect_pages(db)
        print(f"  {db['pref']}: {len(pages)} ページ")
        all_pages.extend(pages)
    print(f"合計: {len(all_pages)} ページ")

    # Chunk
    print("\nチャンク化中...")
    all_chunks = []
    for page in all_pages:
        chunks = chunk_text(page["text"])
        for chunk in chunks:
            all_chunks.append({
                "pref": page["pref"],
                "title": page["title"],
                "page_num": page["page_num"],
                "text": chunk,
            })
    print(f"合計: {len(all_chunks)} チャンク")

    # Check for existing progress (resume support)
    rag_conn = init_rag_db(RAG_DB_PATH)

    # Embed in batches
    print(f"\nEmbedding生成中（バッチサイズ={BATCH_SIZE}）...")
    total = len(all_chunks)
    inserted = 0
    batch_texts = []
    batch_meta = []

    for i, chunk in enumerate(all_chunks):
        batch_texts.append(chunk["text"])
        batch_meta.append(chunk)

        if len(batch_texts) >= BATCH_SIZE or i == total - 1:
            embeddings = embed_batch(batch_texts)
            for meta, emb in zip(batch_meta, embeddings):
                if emb is not None:
                    blob = float_list_to_blob(emb)
                    rag_conn.execute(
                        "INSERT INTO chunks (prefecture, doc_title, page_num, chunk_text, embedding) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (meta["pref"], meta["title"], meta["page_num"], meta["text"], blob),
                    )
                    inserted += 1

            if (i + 1) % (BATCH_SIZE * 10) == 0 or i == total - 1:
                rag_conn.commit()
                pct = (i + 1) / total * 100
                print(f"  {i+1}/{total} ({pct:.1f}%) — {inserted} チャンク保存済み")

            batch_texts = []
            batch_meta = []
            time.sleep(SLEEP_SEC)

    rag_conn.commit()
    rag_conn.close()

    print(f"\n完了! {inserted}/{total} チャンクを保存")
    print(f"DB: {RAG_DB_PATH}")
    print(f"サイズ: {RAG_DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()

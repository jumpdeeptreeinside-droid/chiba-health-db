#!/usr/bin/env python3
"""RAG検索エンジン: Embeddingベクトルによるコサイン類似度検索。"""

from __future__ import annotations

import os
import sqlite3
import struct
from pathlib import Path
from typing import Optional

import numpy as np
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
RAG_DB_PATH = BASE_DIR / "rag_medical_plans.db"


def embed_query(text: str) -> list[float] | None:
    """Gemini Embedding APIでクエリをベクトル化する。"""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-embedding-001:embedContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "content": {"parts": [{"text": text}]},
        "taskType": "RETRIEVAL_QUERY",
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["embedding"]["values"]
    except Exception as e:
        print(f"Embedding error: {e}")
        return None


def blob_to_array(blob: bytes) -> np.ndarray:
    """BLOBからnumpy float32配列に変換。"""
    n = len(blob) // 4
    return np.array(struct.unpack(f"{n}f", blob), dtype=np.float32)


def search(
    query: str,
    top_k: int = 10,
    prefecture_filter: list[str] | None = None,
) -> list[dict]:
    """
    1. queryをGemini Embeddingでベクトル化
    2. chunksテーブルの全embeddingとコサイン類似度を計算
    3. 上位top_k件を返す
    """
    query_vec = embed_query(query)
    if query_vec is None:
        return []

    q = np.array(query_vec, dtype=np.float32)
    q_norm = np.linalg.norm(q)
    if q_norm == 0:
        return []
    q = q / q_norm

    conn = sqlite3.connect(RAG_DB_PATH)
    cur = conn.cursor()

    if prefecture_filter:
        placeholders = ",".join("?" * len(prefecture_filter))
        sql = f"SELECT id, prefecture, doc_title, page_num, chunk_text, embedding FROM chunks WHERE prefecture IN ({placeholders})"
        cur.execute(sql, prefecture_filter)
    else:
        cur.execute("SELECT id, prefecture, doc_title, page_num, chunk_text, embedding FROM chunks")

    results = []
    for row in cur.fetchall():
        cid, pref, title, page_num, text, blob = row
        vec = blob_to_array(blob)
        norm = np.linalg.norm(vec)
        if norm == 0:
            continue
        similarity = float(np.dot(q, vec / norm))
        results.append({
            "id": cid,
            "prefecture": pref,
            "doc_title": title,
            "page_num": page_num,
            "chunk_text": text,
            "similarity": similarity,
        })

    conn.close()

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]


def get_prefectures() -> list[str]:
    """RAG DBに含まれる都道府県一覧を返す。"""
    conn = sqlite3.connect(RAG_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT prefecture FROM chunks ORDER BY prefecture")
    prefs = [r[0] for r in cur.fetchall()]
    conn.close()
    return prefs


if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "在宅医療の数値目標"
    print(f"検索: {query}\n")

    results = search(query, top_k=5)
    for i, r in enumerate(results, 1):
        print(f"{i}. [{r['prefecture']}] {r['doc_title']} p.{r['page_num']} "
              f"(類似度: {r['similarity']:.3f})")
        print(f"   {r['chunk_text'][:100]}...")
        print()

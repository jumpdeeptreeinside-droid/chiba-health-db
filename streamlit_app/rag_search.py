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
import streamlit as st

DB_FILENAME = "rag_medical_plans.db"
DB_URL = "https://github.com/jumpdeeptreeinside-droid/chiba-health-db/releases/download/v1.0/rag_medical_plans.db"
DATA_DIR = Path(__file__).resolve().parent / "data"
RAG_DB_PATH = DATA_DIR / DB_FILENAME


def get_gemini_api_key() -> str:
    """Streamlit Secretsまたは環境変数からAPIキーを取得。"""
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return os.environ.get("GEMINI_API_KEY", "")


def ensure_db() -> Path:
    """DBファイルが無ければGitHub Releasesからダウンロードする。"""
    if RAG_DB_PATH.exists():
        return RAG_DB_PATH

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    st.info("データベースを初回ダウンロード中です（約614MB）。しばらくお待ちください...")
    progress = st.progress(0)

    resp = requests.get(DB_URL, stream=True, timeout=600)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0

    with open(RAG_DB_PATH, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                progress.progress(min(downloaded / total, 1.0))

    progress.empty()
    st.success("データベースのダウンロードが完了しました。")
    return RAG_DB_PATH


def embed_query(text: str) -> list[float] | None:
    """Gemini Embedding APIでクエリをベクトル化する。"""
    api_key = get_gemini_api_key()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-embedding-001:embedContent?key={api_key}"
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
        st.error(f"Embedding error: {e}")
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
    """ベクトル検索: クエリとチャンクのコサイン類似度で上位top_k件を返す。"""
    db_path = ensure_db()
    query_vec = embed_query(query)
    if query_vec is None:
        return []

    q = np.array(query_vec, dtype=np.float32)
    q_norm = np.linalg.norm(q)
    if q_norm == 0:
        return []
    q = q / q_norm

    conn = sqlite3.connect(db_path)
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
    db_path = ensure_db()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT prefecture FROM chunks ORDER BY prefecture")
    prefs = [r[0] for r in cur.fetchall()]
    conn.close()
    return prefs

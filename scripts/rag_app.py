#!/usr/bin/env python3
"""全国医療計画 RAG横断検索 Streamlit アプリ。"""

import os
from pathlib import Path

import streamlit as st
import requests
from dotenv import load_dotenv

from rag_search import search, get_prefectures

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

st.set_page_config(page_title="全国医療計画 RAG検索", page_icon="🏥", layout="wide")
st.title("全国医療計画 RAG横断検索システム")
st.caption("47都道府県の地域医療計画PDFをEmbeddingベクトルで横断検索します")

# --- Sidebar: filters ---
with st.sidebar:
    st.header("検索設定")
    try:
        all_prefs = get_prefectures()
    except Exception:
        all_prefs = []

    selected_prefs = st.multiselect(
        "都道府県フィルタ（空欄＝全国）",
        options=all_prefs,
        default=[],
    )
    top_k = st.slider("検索件数", min_value=3, max_value=30, value=10)
    generate_answer = st.checkbox("Gemini AIで回答を生成する", value=True)

# --- Main: query input ---
query = st.text_input(
    "質問を入力してください",
    placeholder="在宅医療の数値目標について各県ではどう設定していますか？",
)

if st.button("検索", type="primary") and query:
    pref_filter = selected_prefs if selected_prefs else None

    with st.spinner("ベクトル検索中..."):
        results = search(query, top_k=top_k, prefecture_filter=pref_filter)

    if not results:
        st.warning("関連する情報が見つかりませんでした。")
    else:
        # --- Answer generation ---
        if generate_answer:
            with st.spinner("Gemini AIが回答を生成中..."):
                context = "\n\n".join([
                    f"【{r['prefecture']}】{r['doc_title']} p.{r['page_num']}\n{r['chunk_text'][:600]}"
                    for r in results[:8]
                ])
                prompt = f"""あなたは日本の医療政策の専門家アシスタントです。
以下の全国の地域医療計画の抜粋をもとに、質問に答えてください。
抜粋に含まれない情報は「資料には記載がありません」と答えてください。
都道府県ごとの違いや共通点があれば整理して示してください。
回答の最後に、参照した都道府県・資料名・ページ番号を列挙してください。

## 資料の抜粋
{context}

## 質問
{query}

## 回答（日本語・簡潔に）"""

                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
                    resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
                    resp.raise_for_status()
                    answer = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    st.subheader("回答")
                    st.markdown(answer)
                except Exception as e:
                    st.error(f"回答生成エラー: {e}")

        # --- Search results ---
        st.subheader("参照元")
        for i, r in enumerate(results, 1):
            score_pct = r["similarity"] * 100
            with st.expander(
                f"{i}. [{r['prefecture']}] {r['doc_title']} p.{r['page_num']} "
                f"（類似度: {r['similarity']:.3f}）"
            ):
                st.markdown(f"**都道府県:** {r['prefecture']}")
                st.markdown(f"**文書:** {r['doc_title']}")
                st.markdown(f"**ページ:** {r['page_num']}")
                st.progress(min(score_pct / 100, 1.0))
                st.text(r["chunk_text"])

#!/usr/bin/env python3
"""
座標が0/NULLの薬局に対して、国土地理院APIで住所→緯度経度のジオコーディングを行う
API: https://msearch.gsi.go.jp/address-search/AddressSearch?q=ADDRESS
無料・APIキー不要・1リクエスト/秒
"""

import json
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

GSI_API = "https://msearch.gsi.go.jp/address-search/AddressSearch"


def clean_address(address):
    """ジオコーディング用に住所をクリーニング"""
    if not address:
        return None
    # ビル名・階数・部屋番号を除去
    addr = re.sub(r'[（(][^)）]*[)）]', '', address)
    addr = re.sub(r'\d+[FＦ階].*$', '', addr)
    addr = re.sub(r'[A-Za-zＡ-Ｚａ-ｚ]+ビル.*$', '', addr)
    addr = re.sub(r'[A-Za-zＡ-Ｚａ-ｚ]+タワー.*$', '', addr)
    # 全角→半角数字
    addr = addr.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
    # 丁目・番地以降を簡略化（精度向上のため残す）
    addr = addr.strip()
    return addr if addr else None


def geocode(address):
    """国土地理院APIでジオコーディング"""
    cleaned = clean_address(address)
    if not cleaned:
        return None, None

    # まず完全住所で検索
    for query in [cleaned, re.sub(r'\d+[-ー－]\d+.*$', '', cleaned)]:
        try:
            url = f"{GSI_API}?q={urllib.parse.quote(query)}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            if data and len(data) > 0:
                coords = data[0]["geometry"]["coordinates"]
                return coords[1], coords[0]  # lat, lon
        except Exception:
            pass

    return None, None


def process_db(db_path, label):
    print(f"\n{'='*50}")
    print(f"ジオコーディング: {label}")
    print(f"DB: {db_path}")
    print(f"{'='*50}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, address FROM pharmacies
        WHERE (lat = 0 OR lon = 0 OR lat IS NULL OR lon IS NULL)
        AND address IS NOT NULL AND address != ''
    """)
    targets = cur.fetchall()
    print(f"  対象: {len(targets)}件")

    if not targets:
        print("  ジオコーディング不要")
        conn.close()
        return

    success = 0
    failed = 0
    failed_ids = []

    for i, (pid, address) in enumerate(targets):
        lat, lon = geocode(address)

        if lat and lon and lat > 1 and lon > 1:
            cur.execute("UPDATE pharmacies SET lat=?, lon=? WHERE id=?",
                        (lat, lon, pid))
            success += 1
        else:
            failed += 1
            if failed <= 10:
                failed_ids.append((pid, address[:40]))

        if (i + 1) % 100 == 0:
            conn.commit()
            print(f"  進捗: {i+1}/{len(targets)} (成功={success}, 失敗={failed})")

        time.sleep(0.5)  # API負荷軽減

    conn.commit()

    print(f"\n  完了: 成功={success}, 失敗={failed}")
    if failed_ids:
        print("  失敗サンプル:")
        for pid, addr in failed_ids:
            print(f"    ID {pid}: {addr}")

    # 結果確認
    cur.execute("SELECT COUNT(*) FROM pharmacies WHERE lat > 1 AND lon > 1")
    valid = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM pharmacies")
    total = cur.fetchone()[0]
    print(f"\n  有効座標: {valid}/{total} ({valid/total*100:.1f}%)")

    conn.close()


if __name__ == "__main__":
    targets = []

    chiba_db = Path.home() / "chiba_pdf_db" / "chiba_iryo.db"
    osaka_db = Path.home() / "osaka_pdf_db" / "osaka_iryo.db"

    if chiba_db.exists():
        targets.append((chiba_db, "千葉県"))
    if osaka_db.exists():
        targets.append((osaka_db, "大阪府"))

    for db_path, label in targets:
        process_db(db_path, label)

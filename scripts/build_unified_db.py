#!/usr/bin/env python3
"""
build_unified_db.py — 全47都道府県の医療DBを統合して crosshealth.db を作成する。

ソース:
  - ~/chiba_pdf_db/chiba_iryo.db（千葉: 12）
  - ~/osaka_pdf_db/osaka_iryo.db（大阪: 27）
  - ~/prefdb_XX_県名/XX_iryo.db（その他45県）

出力: ~/chiba_pdf_db/crosshealth.db
"""

import sqlite3
import os
import glob
import sys
from pathlib import Path
from datetime import datetime

HOME = Path.home()
OUTPUT_DB = HOME / "chiba_pdf_db" / "crosshealth.db"

# 都道府県コード→名前→地方区分
PREFECTURES = {
    1: ("北海道", "北海道"), 2: ("青森県", "東北"), 3: ("岩手県", "東北"),
    4: ("宮城県", "東北"), 5: ("秋田県", "東北"), 6: ("山形県", "東北"),
    7: ("福島県", "東北"), 8: ("茨城県", "関東"), 9: ("栃木県", "関東"),
    10: ("群馬県", "関東"), 11: ("埼玉県", "関東"), 12: ("千葉県", "関東"),
    13: ("東京都", "関東"), 14: ("神奈川県", "関東"), 15: ("新潟県", "中部"),
    16: ("富山県", "中部"), 17: ("石川県", "中部"), 18: ("福井県", "中部"),
    19: ("山梨県", "中部"), 20: ("長野県", "中部"), 21: ("岐阜県", "中部"),
    22: ("静岡県", "中部"), 23: ("愛知県", "中部"), 24: ("三重県", "近畿"),
    25: ("滋賀県", "近畿"), 26: ("京都府", "近畿"), 27: ("大阪府", "近畿"),
    28: ("兵庫県", "近畿"), 29: ("奈良県", "近畿"), 30: ("和歌山県", "近畿"),
    31: ("鳥取県", "中国"), 32: ("島根県", "中国"), 33: ("岡山県", "中国"),
    34: ("広島県", "中国"), 35: ("山口県", "中国"), 36: ("徳島県", "四国"),
    37: ("香川県", "四国"), 38: ("愛媛県", "四国"), 39: ("高知県", "四国"),
    40: ("福岡県", "九州"), 41: ("佐賀県", "九州"), 42: ("長崎県", "九州"),
    43: ("熊本県", "九州"), 44: ("大分県", "九州"), 45: ("宮崎県", "九州"),
    46: ("鹿児島県", "九州"), 47: ("沖縄県", "九州"),
}


def find_source_dbs():
    """各都道府県のソースDBパスを検出する。"""
    sources = {}
    for code, (name, _) in PREFECTURES.items():
        if code == 12:
            p = HOME / "chiba_pdf_db" / "chiba_iryo.db"
        elif code == 27:
            p = HOME / "osaka_pdf_db" / "osaka_iryo.db"
        else:
            code_str = f"{code:02d}"
            pattern = str(HOME / f"prefdb_{code_str}_*" / f"{code_str}_iryo.db")
            matches = glob.glob(pattern)
            p = Path(matches[0]) if matches else None
        if p and p.exists():
            sources[code] = p
        else:
            print(f"  [SKIP] {code:02d} {name}: DB not found")
    return sources


def create_schema(conn):
    """統合DBのスキーマを作成する。"""
    c = conn.cursor()

    c.executescript("""
    -- マスター
    CREATE TABLE IF NOT EXISTS prefectures (
        code INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        region TEXT
    );

    -- データリネージュ
    CREATE TABLE IF NOT EXISTS data_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_name TEXT,
        source_name TEXT,
        source_url TEXT,
        update_frequency TEXT,
        last_updated TEXT,
        next_check TEXT,
        notes TEXT
    );

    -- 供給層
    CREATE TABLE IF NOT EXISTS pharmacies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prefecture TEXT NOT NULL,
        gmis_id TEXT, name TEXT NOT NULL, address TEXT,
        lat REAL, lon REAL, city_code INTEGER,
        iryo_ken TEXT, homepage TEXT, data_date TEXT,
        ds_only INTEGER DEFAULT 0, chain_name TEXT,
        func_kakaritsuke INTEGER DEFAULT 0,
        func_chiiki_shien INTEGER DEFAULT 0,
        func_zaitaku_sogo INTEGER DEFAULT 0,
        func_mukin INTEGER DEFAULT 0,
        func_zaitaku_cv INTEGER DEFAULT 0,
        func_zaitaku_mayaku INTEGER DEFAULT 0,
        func_medical_dx INTEGER DEFAULT 0,
        func_generic INTEGER DEFAULT 0,
        func_renkei_kyoka INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS medical_facilities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prefecture TEXT NOT NULL,
        name TEXT, category TEXT, address TEXT,
        lat REAL, lon REAL, municipality TEXT,
        medical_area TEXT, beds INTEGER, data_source TEXT
    );

    CREATE TABLE IF NOT EXISTS nursing_care_facilities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prefecture TEXT NOT NULL,
        name TEXT, category TEXT, address TEXT,
        lat REAL, lon REAL, beds INTEGER, data_source TEXT
    );

    -- 需要層
    CREATE TABLE IF NOT EXISTS population_mesh (
        mesh_code TEXT PRIMARY KEY,
        prefecture TEXT NOT NULL,
        lat REAL, lon REAL, population INTEGER,
        municipality TEXT, medical_area TEXT,
        pop_2025 INTEGER, pop_2030 INTEGER, pop_2035 INTEGER,
        pop_2040 INTEGER, pop_2050 INTEGER,
        elderly_65_2025 INTEGER, elderly_75_2025 INTEGER,
        elderly_65_2030 INTEGER, elderly_75_2030 INTEGER,
        elderly_65_2035 INTEGER, elderly_75_2035 INTEGER,
        elderly_65_2040 INTEGER, elderly_75_2040 INTEGER,
        elderly_65_2050 INTEGER, elderly_75_2050 INTEGER,
        access_phar_5km REAL
    );

    -- 疾患・医療需要
    CREATE TABLE IF NOT EXISTS disease_burden (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prefecture TEXT NOT NULL,
        municipality TEXT, medical_area TEXT,
        disease_name TEXT, patient_count INTEGER,
        medical_cost REAL, year INTEGER, data_source TEXT
    );

    CREATE TABLE IF NOT EXISTS medical_procedures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prefecture TEXT NOT NULL,
        category TEXT, procedure_name TEXT,
        count INTEGER, year INTEGER, data_source TEXT
    );

    CREATE TABLE IF NOT EXISTS drug_prescriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prefecture TEXT NOT NULL,
        drug_category TEXT, drug_category_code TEXT,
        setting TEXT, quantity REAL, year INTEGER, data_source TEXT
    );

    -- 人材
    CREATE TABLE IF NOT EXISTS physician_distribution (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prefecture TEXT NOT NULL,
        area TEXT, specialty TEXT,
        physician_count INTEGER, per_100k_population REAL,
        year INTEGER, data_source TEXT
    );

    -- 政策（テキスト）
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prefecture TEXT NOT NULL,
        filename TEXT, title TEXT, total_pages INTEGER
    );

    CREATE TABLE IF NOT EXISTS pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_id INTEGER, page_num INTEGER, text TEXT,
        FOREIGN KEY(doc_id) REFERENCES documents(id)
    );

    CREATE TABLE IF NOT EXISTS municipal_health_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prefecture TEXT NOT NULL,
        municipality TEXT, medical_area TEXT,
        plan_name TEXT, page_number INTEGER,
        content TEXT, source_url TEXT
    );

    -- 統計
    CREATE TABLE IF NOT EXISTS emergency_transport (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prefecture TEXT NOT NULL,
        transport_count INTEGER, avg_response_time REAL,
        avg_hospital_time REAL, difficulty_count INTEGER,
        year INTEGER, data_source TEXT
    );

    CREATE TABLE IF NOT EXISTS medical_costs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prefecture TEXT NOT NULL,
        cost_per_capita REAL, cost_total REAL,
        year INTEGER, data_source TEXT
    );
    """)
    conn.commit()


def get_source_columns(src_conn, table_name):
    """ソーステーブルのカラム名リストを取得する。"""
    cur = src_conn.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cur.fetchall()]


def get_dest_columns(dest_conn, table_name):
    """統合DBテーブルのカラム名リストを取得する。"""
    cur = dest_conn.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cur.fetchall()]


# テーブルごとの統合設定
# key: 統合DBテーブル名
# value: dict with
#   src_table: ソーステーブル名（省略時はkeyと同じ）
#   has_prefecture: ソースに既にprefecture列があるか
#   skip_id: IDを再採番するか
#   is_mesh: mesh_codeがPKで特殊処理
TABLE_CONFIG = {
    "pharmacies": {"has_prefecture": False, "skip_id": True},
    "medical_facilities": {"has_prefecture": False, "skip_id": True},
    "nursing_care_facilities": {"has_prefecture": True, "skip_id": True},
    "population_mesh": {"has_prefecture": False, "skip_id": False, "is_mesh": True},
    "disease_burden": {"has_prefecture": False, "skip_id": True},
    "medical_procedures": {"has_prefecture": True, "skip_id": True},
    "drug_prescriptions": {"has_prefecture": True, "skip_id": True},
    "physician_distribution": {"has_prefecture": True, "skip_id": True},
    "documents": {"has_prefecture": False, "skip_id": True},
    "pages": {"has_prefecture": False, "skip_id": True, "has_doc_fk": True},
    "municipal_health_plans": {"has_prefecture": False, "skip_id": True},
    "emergency_transport": {"has_prefecture": True, "skip_id": True},
    "medical_costs": {"has_prefecture": True, "skip_id": True},
}


def table_exists(conn, table_name):
    cur = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cur.fetchone()[0] > 0


def copy_table(src_conn, dest_conn, table_name, pref_name, config, doc_id_map=None):
    """ソースDBの1テーブルを統合DBにコピーする。"""
    if not table_exists(src_conn, table_name):
        return 0, {}

    src_cols = get_source_columns(src_conn, table_name)
    dest_cols = get_dest_columns(dest_conn, table_name)

    # ソースとデスト両方に存在するカラムを特定（idは再採番するのでスキップ）
    skip_cols = set()
    if config.get("skip_id"):
        skip_cols.add("id")
    if config.get("is_mesh"):
        skip_cols.discard("mesh_code")  # mesh_codeはPKだがコピーする

    common_cols = [c for c in src_cols if c in dest_cols and c not in skip_cols]

    # prefectureがソースに無い場合は追加
    need_add_pref = "prefecture" in dest_cols and not config.get("has_prefecture")
    # ソースにprefectureがあっても空の場合がある → 上書き
    if "prefecture" in src_cols and not config.get("has_prefecture"):
        # ソースにprefecture列はあるがhas_prefecture=False → 上書きする
        pass

    # doc_id FK対応（pagesテーブル）
    has_doc_fk = config.get("has_doc_fk", False)

    select_cols = ", ".join(f'"{c}"' for c in common_cols)
    rows = src_conn.execute(f"SELECT {select_cols} FROM {table_name}").fetchall()

    if not rows:
        return 0, {}

    # 挿入先カラムを構築
    insert_cols = list(common_cols)
    if need_add_pref and "prefecture" not in insert_cols:
        insert_cols.append("prefecture")

    id_map = {}
    dest_cur = dest_conn.cursor()
    count = 0
    for row in rows:
        values = dict(zip(common_cols, row))

        # prefecture列を設定
        if need_add_pref:
            values["prefecture"] = pref_name
        elif "prefecture" in values and not values.get("prefecture"):
            values["prefecture"] = pref_name

        # doc_id FKのリマッピング
        if has_doc_fk and doc_id_map and "doc_id" in values:
            old_doc_id = values["doc_id"]
            values["doc_id"] = doc_id_map.get(old_doc_id, old_doc_id)

        col_names = ", ".join(f'"{c}"' for c in insert_cols)
        placeholders = ", ".join("?" for _ in insert_cols)
        vals = [values.get(c) for c in insert_cols]

        if config.get("is_mesh"):
            # mesh_codeはPK → INSERT OR IGNORE
            dest_cur.execute(
                f"INSERT OR IGNORE INTO {table_name} ({col_names}) VALUES ({placeholders})",
                vals
            )
        else:
            dest_cur.execute(
                f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})",
                vals
            )
            # ID mapping for documents (needed by pages FK)
            if table_name == "documents":
                old_id = values.get("id") if "id" in common_cols else None
                new_id = dest_cur.lastrowid
                if old_id is not None:
                    id_map[old_id] = new_id

        count += 1

    return count, id_map


def create_indexes(conn):
    """インデックスを作成する。"""
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_phar_pref ON pharmacies(prefecture)",
        "CREATE INDEX IF NOT EXISTS idx_phar_latlon ON pharmacies(lat, lon)",
        "CREATE INDEX IF NOT EXISTS idx_phar_iryo ON pharmacies(iryo_ken)",
        "CREATE INDEX IF NOT EXISTS idx_medfac_pref ON medical_facilities(prefecture)",
        "CREATE INDEX IF NOT EXISTS idx_medfac_latlon ON medical_facilities(lat, lon)",
        "CREATE INDEX IF NOT EXISTS idx_medfac_area ON medical_facilities(medical_area)",
        "CREATE INDEX IF NOT EXISTS idx_ncf_pref ON nursing_care_facilities(prefecture)",
        "CREATE INDEX IF NOT EXISTS idx_mesh_pref ON population_mesh(prefecture)",
        "CREATE INDEX IF NOT EXISTS idx_mesh_pop ON population_mesh(population)",
        "CREATE INDEX IF NOT EXISTS idx_db_pref ON disease_burden(prefecture)",
        "CREATE INDEX IF NOT EXISTS idx_mp_pref ON medical_procedures(prefecture)",
        "CREATE INDEX IF NOT EXISTS idx_dp_pref ON drug_prescriptions(prefecture)",
        "CREATE INDEX IF NOT EXISTS idx_pd_pref ON physician_distribution(prefecture)",
        "CREATE INDEX IF NOT EXISTS idx_doc_pref ON documents(prefecture)",
        "CREATE INDEX IF NOT EXISTS idx_pages_docid ON pages(doc_id)",
        "CREATE INDEX IF NOT EXISTS idx_mhp_pref ON municipal_health_plans(prefecture)",
        "CREATE INDEX IF NOT EXISTS idx_mhp_muni ON municipal_health_plans(municipality)",
        "CREATE INDEX IF NOT EXISTS idx_et_pref ON emergency_transport(prefecture)",
        "CREATE INDEX IF NOT EXISTS idx_mc_pref ON medical_costs(prefecture)",
    ]
    for idx in indexes:
        conn.execute(idx)
    conn.commit()


def create_fts(conn):
    """FTS5テーブルを構築する。"""
    conn.executescript("""
    DROP TABLE IF EXISTS pages_fts;
    CREATE VIRTUAL TABLE pages_fts USING fts5(text, content=pages, content_rowid=id);
    INSERT INTO pages_fts(rowid, text) SELECT id, text FROM pages;

    DROP TABLE IF EXISTS municipal_health_plans_fts;
    CREATE VIRTUAL TABLE municipal_health_plans_fts USING fts5(
        content, content=municipal_health_plans, content_rowid=id
    );
    INSERT INTO municipal_health_plans_fts(rowid, content)
        SELECT id, content FROM municipal_health_plans;
    """)
    conn.commit()


def insert_data_sources(conn):
    """データリネージュ情報を投入する。"""
    today = datetime.now().strftime("%Y-%m-%d")
    sources = [
        ("pharmacies", "厚労省GMIS薬局機能情報",
         "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/open_data.html",
         "biyearly", today, None, "全国薬局機能情報提供制度オープンデータ"),
        ("pharmacies(func)", "各地方厚生局施設基準",
         "https://kouseikyoku.mhlw.go.jp",
         "monthly", today, None, "施設基準届出受理一覧から機能フラグを付与"),
        ("medical_facilities", "各地方厚生局指定一覧",
         "https://kouseikyoku.mhlw.go.jp",
         "monthly", today, None, "保険医療機関・薬局の指定一覧"),
        ("population_mesh", "国土数値情報メッシュ推計人口",
         "https://nlftp.mlit.go.jp",
         "quinquennial", today, None, "500mメッシュ人口（2020国勢調査ベース）+ 将来推計"),
        ("disease_burden", "厚労省NDBオープンデータ",
         "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000177221.html",
         "yearly", today, None, "NDB特定健診・レセプトデータ"),
        ("medical_procedures", "厚労省NDBオープンデータ",
         "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000177221.html",
         "yearly", today, None, "NDB診療行為データ"),
        ("drug_prescriptions", "厚労省NDBオープンデータ",
         "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000177221.html",
         "yearly", today, None, "NDB薬剤処方データ"),
        ("physician_distribution", "厚労省医師統計",
         "https://www.e-stat.go.jp",
         "biyearly", today, None, "医師・歯科医師・薬剤師統計"),
        ("documents/pages", "各都道府県公式サイト",
         "https://www.pref.XX.lg.jp",
         "sexennial", today, None, "保健医療計画PDF"),
        ("nursing_care_facilities", "WAM NET介護事業所検索",
         "https://www.kaigokensaku.mhlw.go.jp",
         "yearly", today, None, "介護サービス情報公表システム"),
        ("emergency_transport", "消防庁救急搬送統計",
         "https://www.fdma.go.jp",
         "yearly", today, None, "救急搬送における実態調査"),
        ("medical_costs", "厚労省医療費の動向",
         "https://www.mhlw.go.jp",
         "yearly", today, None, "医療費の地域差分析"),
    ]
    conn.executemany(
        """INSERT INTO data_sources (table_name, source_name, source_url,
           update_frequency, last_updated, next_check, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        sources
    )
    conn.commit()


def main():
    print("=" * 60)
    print("CrossHealth Healthcare DB — 統合ビルド")
    print("=" * 60)

    # 既存DBを削除して新規作成
    if OUTPUT_DB.exists():
        bak = OUTPUT_DB.with_suffix(f".db.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        OUTPUT_DB.rename(bak)
        print(f"既存DBをバックアップ: {bak.name}")

    print(f"\n出力先: {OUTPUT_DB}")

    # ソースDB検出
    print("\n--- ソースDB検出 ---")
    sources = find_source_dbs()
    print(f"\n検出: {len(sources)}/47 都道府県")

    # 統合DB作成
    dest_conn = sqlite3.connect(str(OUTPUT_DB))
    dest_conn.execute("PRAGMA journal_mode=WAL")
    dest_conn.execute("PRAGMA synchronous=NORMAL")

    print("\n--- スキーマ作成 ---")
    create_schema(dest_conn)

    # prefecturesマスター投入
    for code, (name, region) in PREFECTURES.items():
        dest_conn.execute(
            "INSERT OR REPLACE INTO prefectures (code, name, region) VALUES (?, ?, ?)",
            (code, name, region)
        )
    dest_conn.commit()
    print("prefecturesマスター: 47件投入")

    # 各県のデータを統合
    print("\n--- データ統合 ---")
    stats = {}
    for code in sorted(sources.keys()):
        src_path = sources[code]
        pref_name = PREFECTURES[code][0]
        print(f"\n[{code:02d}] {pref_name}: {src_path.name}")

        src_conn = sqlite3.connect(str(src_path))

        doc_id_map = {}
        for table_name, config in TABLE_CONFIG.items():
            # pagesは後でdocumentsのID mapを使う
            if table_name == "pages":
                continue
            count, id_map = copy_table(src_conn, dest_conn, table_name, pref_name, config)
            if table_name == "documents":
                doc_id_map = id_map
            if count > 0:
                stats.setdefault(table_name, 0)
                stats[table_name] += count
                print(f"  {table_name}: {count:,}件")

        # pagesテーブル（doc_id FKのリマッピングが必要）
        config = TABLE_CONFIG["pages"]
        count, _ = copy_table(src_conn, dest_conn, "pages", pref_name, config, doc_id_map)
        if count > 0:
            stats.setdefault("pages", 0)
            stats["pages"] += count
            print(f"  pages: {count:,}件")

        dest_conn.commit()
        src_conn.close()

    # インデックス作成
    print("\n--- インデックス作成 ---")
    create_indexes(dest_conn)
    print("完了")

    # FTS構築
    print("\n--- FTS構築 ---")
    create_fts(dest_conn)
    print("完了")

    # データリネージュ投入
    print("\n--- データリネージュ投入 ---")
    insert_data_sources(dest_conn)
    print("完了")

    # VACUUM
    print("\n--- VACUUM ---")
    dest_conn.execute("VACUUM")
    dest_conn.close()

    # サマリー
    db_size = OUTPUT_DB.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 60)
    print("統合完了!")
    print(f"DB: {OUTPUT_DB} ({db_size:.1f} MB)")
    print(f"都道府県: {len(sources)}/47")
    print("\nテーブル別レコード数:")
    for t, c in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()

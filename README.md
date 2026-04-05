# CrossHealth Healthcare DB

**全国47都道府県 医療オープンデータベース**
Japan National Healthcare Open Database

日本全国の薬局・医療機関・人口メッシュ・疾患負荷・医療計画データを統合したオープンデータベースです。
[地域医療スポッター](https://note.com/ski_sph) の記事生成パイプライン、薬局出店戦略コンサル、行政向け政策提言のコアインフラとして機能します。

---

## 統合DB (`crosshealth.db`)

| テーブル | レコード数 | 内容 |
|---|---|---|
| `pharmacies` | 69,329 | 全国薬局（GMIS + 施設基準機能フラグ） |
| `medical_facilities` | 161,507 | 病院・診療所・歯科 |
| `nursing_care_facilities` | 91,872 | 介護施設（WAM NET） |
| `population_mesh` | 466,792 | 500mメッシュ人口 + 将来推計 |
| `disease_burden` | 4,537 | NDB疾患リスク指標 |
| `medical_procedures` | 96,619 | NDB診療行為 |
| `drug_prescriptions` | 13,954 | NDB薬剤処方 |
| `physician_distribution` | 280 | 医師分布統計 |
| `documents` / `pages` | 302 / 19,030 | 保健医療計画PDF全文（FTS5検索可） |
| `municipal_health_plans` | 2,301 | 市区町村健康増進計画（FTS5検索可） |
| `emergency_transport` | 47 | 救急搬送統計 |
| `medical_costs` | 48 | 医療費統計 |
| `prefectures` | 47 | 都道府県マスター（地方区分付き） |
| `data_sources` | 12 | データリネージュ（出典・更新頻度） |

---

## プロジェクト構成

```
chiba-health-db/
├── README.md                  ← このファイル
├── crosshealth.db             ← 統合DB（Git LFS）
├── scripts/
│   ├── build_unified_db.py    ← 47都道府県→統合DB
│   ├── build_prefecture.py    ← 県別DB構築
│   ├── enrich_prefecture.py   ← 県別DBエンリッチ
│   ├── add_medical_plan.py    ← 医療計画PDF投入
│   ├── scrape_drugstores.py   ← DS情報スクレイピング
│   ├── geocode_pharmacies.py  ← ジオコーディング
│   ├── make_dashboard_lite.py ← 県別ダッシュボード生成
│   ├── make_national_dashboard.py ← 全国ダッシュボード生成
│   └── analysis_2sfca.py      ← 2SFCA アクセシビリティ分析
├── config/
│   ├── claude_watcher.py      ← タスク自動実行Watcher
│   ├── run_watcher.sh         ← Watcher起動スクリプト
│   ├── com.crosshealth.watcher.plist ← LaunchAgent
│   └── .env.example           ← 環境変数テンプレート
├── dashboards/
│   ├── dashboard_national.html
│   ├── dashboard_chiba.html
│   └── dashboard_osaka.html
└── docs/
    ├── data_sources.md        ← データリネージュ一覧
    └── recovery.md            ← Mac復旧手順
```

---

## クイックスタート

```python
import sqlite3, pandas as pd

conn = sqlite3.connect("crosshealth.db")

# 東京都の薬局を取得
df = pd.read_sql("SELECT * FROM pharmacies WHERE prefecture='東京都'", conn)

# 全国の薬局数を都道府県別に集計
df_summary = pd.read_sql("""
    SELECT prefecture, count(*) as cnt
    FROM pharmacies GROUP BY prefecture ORDER BY cnt DESC
""", conn)

# 保健医療計画を全文検索
results = conn.execute("""
    SELECT d.prefecture, d.filename, p.page_num, snippet(pages_fts, 0, '>>','<<', '...', 32)
    FROM pages_fts f
    JOIN pages p ON p.id = f.rowid
    JOIN documents d ON d.id = p.doc_id
    WHERE pages_fts MATCH '地域包括ケア'
    ORDER BY rank LIMIT 10
""").fetchall()
```

---

## データソース

詳細は [docs/data_sources.md](docs/data_sources.md) を参照。

| ソース | URL | 更新頻度 |
|---|---|---|
| 厚労省GMIS薬局機能情報 | mhlw.go.jp | 2年 |
| 各地方厚生局施設基準 | kouseikyoku.mhlw.go.jp | 毎月 |
| 国土数値情報メッシュ人口 | nlftp.mlit.go.jp | 5年 |
| 厚労省NDBオープンデータ | mhlw.go.jp | 毎年 |
| 厚労省医師統計 | e-stat.go.jp | 2年 |
| WAM NET 介護事業所 | kaigokensaku.mhlw.go.jp | 毎年 |
| 消防庁救急搬送統計 | fdma.go.jp | 毎年 |

---

## 自動化パイプライン

### 地域医療スポッター（記事自動生成）
```
毎週日曜 深夜0時 JST（GitHub Actions）
  → DB から圏域の薬局統計を取得
  → PDF FTS から保健医療計画の関連箇所を抽出
  → Claude API でドラフト記事を生成
  → 人間によるファクトチェック → note 公開
```

### Claude Watcher（タスク自動実行）
```
LaunchAgent が常駐監視
  → inbox/claude_tasks/ に .md ファイルが追加
  → 自動でClaude Code を実行
  → 結果を inbox/claude_results/ に保存
```

---

## 復旧手順

新しいMacでの環境構築は [docs/recovery.md](docs/recovery.md) を参照。

---

**作成・管理:** CrossHealth / 木内翔太
**ライセンス:** データは各出典の利用規約に従います。スクリプトは MIT License。

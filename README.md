# chiba-health-db

**千葉県 地域医療オープンデータベース**
Chiba Prefecture Healthcare Open Database

千葉県の薬局・医療資源・地域医療計画データを統合したオープンデータベースです。
[地域医療スポッター](https://note.com/ski_sph) の記事生成パイプラインのコアインフラとして機能します。

---

## データ構造（Layers）

| Layer | データ | ステータス |
|-------|--------|-----------|
| **Layer 1** | 薬局データ（基本情報・分類・在宅・サービス特性フラグ） | ✅ 完成 |
| **Layer 2** | 人口・地理データ（500mメッシュ・中学校区・市区町村・医療圏境界） | ✅ 完成 |
| **Layer 3** | 千葉県保健医療計画PDF全文検索DB（39本・779ページ FTS5） | ✅ 完成 |
| **Layer 4** | インタラクティブ地図（6人口レイヤー × 薬局3種別） | ✅ 完成 |
| **Layer 5** | 医療機関（病院・診療所・訪問看護・歯科） | 🔜 未着手 |
| **Layer 6** | NDBオープンデータ（疾患別レセプト・医療費・処方傾向） | 🔜 未着手 |
| **Layer 7** | 公共交通アクセス（薬局・医療機関へのアクセス圏） | 🔜 未着手 |
| **Layer 8** | 健康増進計画PDF（千葉県54市区町村） | 🔜 未着手 |

---

## DBテーブル一覧

### pharmacies（3,196件）
千葉県内の薬局マスタ。GMISデータ＋施設基準届出を統合。

| 列名 | 説明 |
|------|------|
| `name` | 薬局名 |
| `address` | 住所 |
| `lat` / `lon` | 緯度・経度 |
| `city_code` | 市区町村コード（3桁） |
| `iryo_ken` | 二次保健医療圏名 |
| `pharmacy_type` | 独立 / NPhA / JACDS |
| `ds_only` | DS専業フラグ（調剤なし=1） |
| `chain_name` | チェーン名 |
| `zaitaku_flag` | 在宅患者訪問薬剤管理指導料 届出（0/1） |
| `zaitaku_enhanced` | 在宅薬学総合体制加算（強化型在宅） |
| `mukin_flag` | 無菌製剤処理加算 |
| `mayaku_iv_flag` | 在宅患者医療用麻薬持続注射療法加算 |
| `tpn_flag` | 在宅中心静脈栄養法加算 |
| `kakari_flag` | かかりつけ薬剤師指導料・包括管理料 |
| `renkei_flag` | 連携強化加算 |
| `chiiki_shien_flag` | 地域支援体制加算（1〜4いずれか） |
| `iryo_dx_flag` | 医療DX推進体制整備加算 |
| `kouhatsu_flag` | 後発医薬品調剤体制加算（いずれか） |
| `tokubetsu_flag` | 特別調剤基本料A（門内薬局相当） |
| `tokutei_kanri_flag` | 特定薬剤管理指導加算2（ハイリスク薬） |

**出典:** 千葉県薬局機能情報（GMIS）2025年12月 / 関東信越厚生局 施設基準届出受理状況 r0803

---

### mesh_population（15,092件）
e-Stat 500mメッシュ人口データ。5歳階級別人口から年齢層比率を算出。

| 列名 | 説明 |
|------|------|
| `mesh_code` | 9桁500mメッシュコード |
| `pop_total` | 総人口 |
| `aging_rate` | 高齢化率（65歳以上） |
| `rate_75over` | 超高齢率（75歳以上） |
| `rate_0_14` | 年少人口比率 |
| `rate_15_39` | 若年層比率 |
| `rate_25_44` | 子育て世代比率 |
| `rate_15_64` | 生産年齢比率 |

**出典:** e-Stat 令和2年国勢調査 500mメッシュ（tblT001141H12 / tblT001192H12）

---

### school_districts（364件）
中学校区ポリゴン。国土数値情報 A32-21_12 + 船橋市26校区（Voronoi近似）。

### city_boundaries（60件）
市区町村境界ポリゴン。iryo_ken 列で二次医療圏との紐付けあり。

### iryo_ken_boundaries（9件）
二次保健医療圏境界ポリゴン（市区町村ポリゴンを dissolve して生成）。

### documents / pages（39件 / 779ページ）
千葉県保健医療計画PDF全文テキスト。FTS5仮想テーブル `pages_fts` で全文検索可能。

---

## 自動化パイプライン（地域医療スポッター）

```
毎週日曜 深夜0時 JST（GitHub Actions）
  ↓
① DB から圏域の薬局統計を取得
② PDF FTS から保健医療計画の関連箇所を抽出
③ Claude API（鷹見ジン）でドラフト記事を生成
④ obsidian-brain に自動コミット
⑤ todo.md に「ファクトチェック待ち」を追記
  ↓
朝のブリーフィングで通知
  ↓
⑥ 人間によるファクトチェック
⑦ note 公開
```

### 記事進捗（地域医療スポッター）

| Vol | 圏域 | ステータス |
|-----|------|-----------|
| Vol.01 | 安房 | ✅ 公開済み |
| Vol.02 | — | ✅ 公開済み |
| Vol.03 | 市原 | ✅ ドラフト完成 |
| Vol.04 | 印旛 | ✅ ドラフト完成（DBフル活用版） |
| Vol.05〜 | 千葉・香取海匝・山武長生夷隅・君津・東葛北部・東葛南部 | 🔜 自動生成待ち |

---

## クイックスタート

```bash
# 薬局データをPythonで読む
import sqlite3, pandas as pd
conn = sqlite3.connect("data/chiba_iryo.db")
df = pd.read_sql("SELECT * FROM pharmacies WHERE iryo_ken='印旛'", conn)

# PDF全文検索
results = conn.execute("""
    SELECT d.filename, p.page_num, p.text
    FROM pages_fts f
    JOIN pages p ON p.id = f.rowid
    JOIN documents d ON d.id = p.doc_id
    WHERE pages_fts MATCH '印旛'
    ORDER BY rank LIMIT 5
""").fetchall()
```

---

## スクリプト一覧

| スクリプト | 役割 |
|-----------|------|
| `scripts/import_mesh_population.py` | e-Stat 500mメッシュ人口インポート |
| `scripts/import_school_districts.py` | 国土数値情報 中学校区インポート |
| `scripts/import_funabashi_districts.py` | 船橋市 Voronoi 校区生成 |
| `scripts/import_boundaries.py` | 市区町村・二次医療圏境界インポート |
| `scripts/add_service_flags.py` | 薬局サービス特性フラグ追加（施設基準届出） |
| `scripts/build_pdf_db.py` | 保健医療計画PDF全文インデックス構築 |
| `scripts/visualize_mesh.py` | インタラクティブ地図生成（output/mesh_map.html） |
| `article_generator/generate_draft.py` | 地域医療スポッター記事自動生成 |

---

## 関連リンク

- [地域医療スポッター（note）](https://note.com/ski_sph)
- [医療政策ウォッチャー](https://github.com/jumpdeeptreeinside-droid/health-policy-watcher)

---

**作成・管理:** CrossHealth / 木内翔太
**ライセンス:** データは各出典の利用規約に従います。スクリプトは MIT License。

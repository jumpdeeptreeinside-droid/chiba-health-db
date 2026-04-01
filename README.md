# chiba-health-db

**千葉県 地域医療オープンデータベース**
Chiba Prefecture Healthcare Open Database

千葉県の薬局・医療資源・地域医療計画データを統合したオープンデータベースです。
[地域医療スポッター](https://note.com/) の記事生成パイプラインも含みます。

---

## データ構造（Layers）

| Layer | データ | ステータス |
|-------|--------|-----------|
| **Layer 1** | 千葉県薬局機能情報（2,997件）+ 在宅対応フラグ | ✅ 公開中 |
| **Layer 2** | 人口メッシュ（e-Stat 250m/500m）| 🔜 準備中 |
| **Layer 3** | NDBオープンデータ（疾患別レセプト）| 🔜 準備中 |
| **Layer 4** | 千葉県54市区町村 健康増進計画PDF | 🔜 準備中 |

---

## ダウンロード

```python
import pandas as pd

# 薬局データ（Parquet）
df = pd.read_parquet(
    "https://github.com/jumpdeeptreeinside-droid/chiba-health-db/raw/main/data/pharmacies.parquet"
)
```

---

## データ定義

### pharmacies テーブル

| 列名 | 説明 |
|------|------|
| `name` | 薬局名 |
| `prefecture` | 都道府県 |
| `city_name` | 市区町村名 |
| `iryo_ken` | 保健医療圏名 |
| `zaitaku_flag` | 在宅患者訪問薬剤管理指導料 届出有無（1=あり） |
| `ds_only` | DS専用店舗フラグ（1=調剤なし） |

**出典:**
- 薬局機能情報: 厚生労働省オープンデータ（2025年12月1日時点）
- 在宅対応フラグ: 関東信越厚生局「施設基準届出受理状況」r0803

---

## 自動化パイプライン

```
毎週日曜 深夜（GitHub Actions）
  ↓
① DBから圏域データを取得
② Claude API でドラフト生成
③ obsidian-brain に自動コミット
  ↓
月曜朝のブリーフィングで通知
  ↓
③ 人間によるファクトチェック
④ note 公開
```

---

## 関連リンク

- [地域医療スポッター（note）](https://note.com/)
- [医療政策ウォッチャー](https://github.com/jumpdeeptreeinside-droid/health-policy-watcher)
- [CrossHealth](https://crosshealth.jp)

---

**作成・管理:** [CrossHealth](https://crosshealth.jp) / 木内翔太
**ライセンス:** データは各出典の利用規約に従います。スクリプトは MIT License。

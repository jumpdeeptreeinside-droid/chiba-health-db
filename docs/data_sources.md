# データリネージュ一覧

CrossHealth Healthcare DB (`crosshealth.db`) のデータソースと更新頻度。

## 供給層

| テーブル | データソース | URL | 更新頻度 |
|---|---|---|---|
| `pharmacies` | 厚労省GMIS薬局機能情報 | mhlw.go.jp/stf/.../open_data.html | 2年ごと |
| `pharmacies` (func_*) | 各地方厚生局施設基準 | kouseikyoku.mhlw.go.jp | 毎月 |
| `medical_facilities` | 各地方厚生局指定一覧 | kouseikyoku.mhlw.go.jp | 毎月 |
| `nursing_care_facilities` | WAM NET 介護事業所検索 | kaigokensaku.mhlw.go.jp | 毎年 |

## 需要層

| テーブル | データソース | URL | 更新頻度 |
|---|---|---|---|
| `population_mesh` | 国土数値情報メッシュ推計人口 | nlftp.mlit.go.jp | 5年ごと |
| `disease_burden` | 厚労省NDBオープンデータ | mhlw.go.jp/.../0000177221 | 毎年 |
| `medical_procedures` | 厚労省NDBオープンデータ | mhlw.go.jp/.../0000177221 | 毎年 |
| `drug_prescriptions` | 厚労省NDBオープンデータ | mhlw.go.jp/.../0000177221 | 毎年 |

## 人材

| テーブル | データソース | URL | 更新頻度 |
|---|---|---|---|
| `physician_distribution` | 厚労省医師統計 | e-stat.go.jp | 2年ごと |

## 政策テキスト

| テーブル | データソース | URL | 更新頻度 |
|---|---|---|---|
| `documents` / `pages` | 各都道府県公式サイト | pref.XX.lg.jp | 6年ごと（医療計画改定） |
| `municipal_health_plans` | 各市区町村公式サイト | 各市.lg.jp | 6年ごと |

## 統計

| テーブル | データソース | URL | 更新頻度 |
|---|---|---|---|
| `emergency_transport` | 消防庁救急搬送統計 | fdma.go.jp | 毎年 |
| `medical_costs` | 厚労省医療費の動向 | mhlw.go.jp | 毎年 |

## 更新スケジュール

- **毎月**: 厚生局施設基準・指定一覧（pharmacies func, medical_facilities）
- **毎年**: NDB, 介護, 救急搬送, 医療費
- **2年ごと**: GMIS薬局情報, 医師統計
- **5年ごと**: 国勢調査ベースメッシュ人口
- **6年ごと**: 保健医療計画PDF

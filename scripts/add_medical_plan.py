#!/usr/bin/env python3
"""
全国都道府県 地域医療計画PDF DB化スクリプト

使い方:
    python3 add_medical_plan.py --code 13        # 東京都
    python3 add_medical_plan.py --code 13 14 11  # 複数県
    python3 add_medical_plan.py --all10           # 主要10都道府県一括
"""

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

import pdfplumber
import requests

# --- 都道府県マスタ ---
PREF_NAMES = {
    1: "北海道", 2: "青森県", 3: "岩手県", 4: "宮城県", 5: "秋田県",
    6: "山形県", 7: "福島県", 8: "茨城県", 9: "栃木県", 10: "群馬県",
    11: "埼玉県", 12: "千葉県", 13: "東京都", 14: "神奈川県", 15: "新潟県",
    16: "富山県", 17: "石川県", 18: "福井県", 19: "山梨県", 20: "長野県",
    21: "岐阜県", 22: "静岡県", 23: "愛知県", 24: "三重県", 25: "滋賀県",
    26: "京都府", 27: "大阪府", 28: "兵庫県", 29: "奈良県", 30: "和歌山県",
    31: "鳥取県", 32: "島根県", 33: "岡山県", 34: "広島県", 35: "山口県",
    36: "徳島県", 37: "香川県", 38: "愛媛県", 39: "高知県", 40: "福岡県",
    41: "佐賀県", 42: "長崎県", 43: "熊本県", 44: "大分県", 45: "宮崎県",
    46: "鹿児島県", 47: "沖縄県",
}

PREF_SHORT = {
    1: "hokkaido", 2: "aomori", 3: "iwate", 4: "miyagi", 5: "akita",
    6: "yamagata", 7: "fukushima", 8: "ibaraki", 9: "tochigi", 10: "gunma",
    11: "saitama", 12: "chiba", 13: "tokyo", 14: "kanagawa", 15: "niigata",
    16: "toyama", 17: "ishikawa", 18: "fukui", 19: "yamanashi", 20: "nagano",
    21: "gifu", 22: "shizuoka", 23: "aichi", 24: "mie", 25: "shiga",
    26: "kyoto", 27: "osaka", 28: "hyogo", 29: "nara", 30: "wakayama",
    31: "tottori", 32: "shimane", 33: "okayama", 34: "hiroshima", 35: "yamaguchi",
    36: "tokushima", 37: "kagawa", 38: "ehime", 39: "kochi",
    40: "fukuoka", 41: "saga", 42: "nagasaki", 43: "kumamoto",
    44: "oita", 45: "miyazaki", 46: "kagoshima", 47: "okinawa",
}

# --- 各都道府県のPDF URL定義 ---
# (filename, title, url)
PREF_PDFS = {
    13: [  # 東京都
        ("tokyo_zenbun.pdf", "東京都保健医療計画（令和6年3月改定）全文",
         "https://www.hokeniryo.metro.tokyo.lg.jp/documents/d/hokeniryo/zenbun_2"),
    ],
    14: [  # 神奈川県
        ("kanagawa_01.pdf", "第1部 総論",
         "https://www.pref.kanagawa.jp/documents/108561/01.pdf"),
        ("kanagawa_02.pdf", "第2部第1章 事業別の医療体制",
         "https://www.pref.kanagawa.jp/documents/108561/02.pdf"),
        ("kanagawa_03.pdf", "第2部第2章 疾病別の医療連携体制",
         "https://www.pref.kanagawa.jp/documents/108561/03.pdf"),
        ("kanagawa_04.pdf", "第2部第3章 未病対策等の推進",
         "https://www.pref.kanagawa.jp/documents/108561/04.pdf"),
        ("kanagawa_05.pdf", "第2部第4章 地域包括ケアシステムの推進",
         "https://www.pref.kanagawa.jp/documents/108561/05.pdf"),
        ("kanagawa_06.pdf", "第2部第5章 医療従事者の確保・養成",
         "https://www.pref.kanagawa.jp/documents/108561/06.pdf"),
        ("kanagawa_07.pdf", "第2部第7章 安全・安心で質の高い医療体制",
         "https://www.pref.kanagawa.jp/documents/108561/07.pdf"),
        ("kanagawa_08.pdf", "第3部 地域医療構想",
         "https://www.pref.kanagawa.jp/documents/108561/08.pdf"),
        ("kanagawa_09.pdf", "第5部 別冊",
         "https://www.pref.kanagawa.jp/documents/108561/09.pdf"),
    ],
    11: [  # 埼玉県
        ("saitama_honbun.pdf", "埼玉県地域保健医療計画（令和6-11年度）本文",
         "https://www.pref.saitama.lg.jp/documents/249628/keikaku2.pdf"),
        ("saitama_siryou.pdf", "埼玉県地域保健医療計画 資料編",
         "https://www.pref.saitama.lg.jp/documents/249628/siryou.pdf"),
    ],
    23: [  # 愛知県
        ("aichi_01_souron.pdf", "はじめに・第1部（総論）",
         "https://www.pref.aichi.jp/uploaded/attachment/526015.pdf"),
        ("aichi_02_iryouken.pdf", "第2部（医療圏及び基準病床数等）",
         "https://www.pref.aichi.jp/uploaded/attachment/507964.pdf"),
        ("aichi_03_1_seibi.pdf", "第3部第1-2章（保健医療施設の整備目標）",
         "https://www.pref.aichi.jp/uploaded/attachment/511847.pdf"),
        ("aichi_03_2_kyukyu.pdf", "第3部第3-9章（救急・災害・感染症等）",
         "https://www.pref.aichi.jp/uploaded/attachment/507966.pdf"),
        ("aichi_03_3_jyuji.pdf", "第3部第10-11章（保健医療従事者確保等）",
         "https://www.pref.aichi.jp/uploaded/attachment/507968.pdf"),
        ("aichi_03_4_2ji.pdf", "第3部第12章（2次医療圏における医療提供体制）",
         "https://www.pref.aichi.jp/uploaded/attachment/507969.pdf"),
        ("aichi_04_gairai.pdf", "第4部（外来医療計画の推進）",
         "https://www.pref.aichi.jp/uploaded/attachment/511701.pdf"),
        ("aichi_05_siryou.pdf", "資料",
         "https://www.pref.aichi.jp/uploaded/attachment/526016.pdf"),
    ],
    40: [  # 福岡県
        ("fukuoka_honpen.pdf", "福岡県保健医療計画 本編",
         "https://www.pref.fukuoka.lg.jp/uploaded/attachment/219436.pdf"),
        ("fukuoka_sankou.pdf", "福岡県保健医療計画 参考資料",
         "https://www.pref.fukuoka.lg.jp/uploaded/attachment/219437.pdf"),
    ],
    1: [  # 北海道
        ("hokkaido_ch1.pdf", "第1章 基本的な考え方",
         "https://www.pref.hokkaido.lg.jp/fs/9/9/7/4/7/5/4/_/01_(%E7%AC%AC1%E7%AB%A0)(%E8%A1%A8%E7%B4%99%E3%80%81%E7%9B%AE%E6%AC%A1%E3%80%81P1~9)240222_%E7%9F%A5%E4%BA%8B%E6%8C%A8%E6%8B%B6%E5%85%A5%E3%82%8A.pdf"),
        ("hokkaido_ch2.pdf", "第2章 地域の現状",
         "https://www.pref.hokkaido.lg.jp/fs/1/0/4/4/5/3/6/7/_/02_(%E7%AC%AC2%E7%AB%A0)(P10~30).pdf"),
        ("hokkaido_ch3_1.pdf", "第3章 5疾病・6事業（第1-9節）",
         "https://www.pref.hokkaido.lg.jp/fs/1/0/4/4/5/3/6/8/_/03-1_(%E7%AC%AC3%E7%AB%A0%20%E7%AC%AC1%E7%AF%80~%E7%AC%AC9%E7%AF%80)(P31~107).pdf"),
        ("hokkaido_ch3_2.pdf", "第3章 5疾病・6事業（第10-13節）",
         "https://www.pref.hokkaido.lg.jp/fs/1/0/4/4/5/3/6/9/_/03-2_(%E7%AC%AC3%E7%AB%A0%20%E7%AC%AC10%E7%AF%80~%E7%AC%AC13%E7%AF%80)(P108~154).pdf"),
        ("hokkaido_ch4.pdf", "第4章 地域保健医療対策の推進",
         "https://www.pref.hokkaido.lg.jp/fs/1/0/4/4/5/3/7/0/_/04_(%E7%AC%AC4%E7%AB%A0)(P155~184).pdf"),
        ("hokkaido_ch5.pdf", "第5章 医療の安全確保",
         "https://www.pref.hokkaido.lg.jp/fs/1/0/3/4/3/4/9/5/_/05_(%E7%AC%AC5%E7%AB%A0)(P185~210).pdf"),
        ("hokkaido_ch6.pdf", "第6章 医師の確保",
         "https://www.pref.hokkaido.lg.jp/fs/1/0/3/6/8/6/5/5/_/06_(%E7%AC%AC6%E7%AB%A0)(P211~250)0627%E4%BF%AE%E6%AD%A3.pdf"),
        ("hokkaido_ch7.pdf", "第7章 医療従事者の確保",
         "https://www.pref.hokkaido.lg.jp/fs/1/0/4/4/5/3/7/1/_/07_(%E7%AC%AC7%E7%AB%A0)(P251~273).pdf"),
        ("hokkaido_ch8.pdf", "第8章 外来医療",
         "https://www.pref.hokkaido.lg.jp/fs/1/0/3/4/3/4/9/8/_/08_(%E7%AC%AC8%E7%AB%A0)(P274~290).pdf"),
        ("hokkaido_ch9.pdf", "第9章 計画の推進と評価",
         "https://www.pref.hokkaido.lg.jp/fs/1/0/4/4/5/3/7/2/_/09_(%E7%AC%AC9%E7%AB%A0)(P291~299).pdf"),
    ],
    4: [  # 宮城県
        ("miyagi_zenbun.pdf", "第8次宮城県地域医療計画 全体版",
         "https://www.pref.miyagi.jp/documents/11391/8jitiikiiryokeikaku_compressed.pdf"),
    ],
    34: [  # 広島県
        ("hiroshima_ch1.pdf", "第1章 総論",
         "https://www.pref.hiroshima.lg.jp/uploaded/attachment/571249.pdf"),
        ("hiroshima_ch2_2.pdf", "第2章第2節 救急医療などの医療連携体制",
         "https://www.pref.hiroshima.lg.jp/uploaded/attachment/571252.pdf"),
        ("hiroshima_ch2_3.pdf", "第2章第3節 在宅医療と介護等の連携体制",
         "https://www.pref.hiroshima.lg.jp/uploaded/attachment/571257.pdf"),
        ("hiroshima_ch2_5.pdf", "第2章第5節 医療に関する情報提供",
         "https://www.pref.hiroshima.lg.jp/uploaded/attachment/571262.pdf"),
        ("hiroshima_ch3.pdf", "第3章 保健医療各分野の総合的な対策",
         "https://www.pref.hiroshima.lg.jp/uploaded/attachment/571263.pdf"),
        ("hiroshima_ch5.pdf", "第5章 保健医療体制を支える人材の確保・育成",
         "https://www.pref.hiroshima.lg.jp/uploaded/attachment/571265.pdf"),
        ("hiroshima_ch8.pdf", "第8章 計画の推進体制と評価の実施",
         "https://www.pref.hiroshima.lg.jp/uploaded/attachment/571279.pdf"),
        ("hiroshima_yougo.pdf", "用語の解説",
         "https://www.pref.hiroshima.lg.jp/uploaded/attachment/571286.pdf"),
    ],
    28: [  # 兵庫県
        ("hyogo_zenbun.pdf", "兵庫県保健医療計画（令和6年4月）全文",
         "https://web.pref.hyogo.lg.jp/kf15/documents/keikakuzenbun.pdf"),
    ],
    47: [  # 沖縄県
        ("okinawa_ch1.pdf", "第1章 総説",
         "https://www.pref.okinawa.lg.jp/_res/projects/default_project/_page_/001/028/660/dai1syou.pdf"),
        ("okinawa_ch2.pdf", "第2章 沖縄県の医療の現状",
         "https://www.pref.okinawa.lg.jp/_res/projects/default_project/_page_/001/028/660/dai2syou.pdf"),
        ("okinawa_ch3.pdf", "第3章 医療圏と基準病床数",
         "https://www.pref.okinawa.lg.jp/_res/projects/default_project/_page_/001/028/660/dai3syou.pdf"),
        ("okinawa_ch4.pdf", "第4章 疾病対策",
         "https://www.pref.okinawa.lg.jp/_res/projects/default_project/_page_/001/028/660/dai4syou.pdf"),
        ("okinawa_ch5_1.pdf", "第5章 医療施策 1/2",
         "https://www.pref.okinawa.lg.jp/_res/projects/default_project/_page_/001/028/660/dai5syou1.pdf"),
        ("okinawa_ch5_2.pdf", "第5章 医療施策 2/2",
         "https://www.pref.okinawa.lg.jp/_res/projects/default_project/_page_/001/028/660/dai5syou2.pdf"),
        ("okinawa_ch6.pdf", "第6章 地域医療構想",
         "https://www.pref.okinawa.lg.jp/_res/projects/default_project/_page_/001/028/660/dai6syou.pdf"),
        ("okinawa_ch7.pdf", "第7章 医療従事者の養成・確保",
         "https://www.pref.okinawa.lg.jp/_res/projects/default_project/_page_/001/028/660/dai7syou.pdf"),
        ("okinawa_ch8.pdf", "第8章 計画の進行管理",
         "https://www.pref.okinawa.lg.jp/_res/projects/default_project/_page_/001/028/660/dai8syou.pdf"),
    ],
    2: [  # 青森県
        ("aomori_zenbun.pdf", "第8次青森県保健医療計画 全文",
         "https://www.pref.aomori.lg.jp/soshiki/kenko/iryo/files/hokeniryoukeikaku.pdf"),
    ],
    3: [  # 岩手県
        ("iwate_honbun.pdf", "岩手県保健医療計画（2024-2029）本文",
         "https://www.pref.iwate.jp/_res/projects/default_project/_page_/001/002/862/02-5.pdf"),
    ],
    5: [  # 秋田県
        ("akita_01_souron.pdf", "秋田県医療保健福祉計画 分割1（総論・地域医療提供体制）",
         "https://www.pref.akita.lg.jp/uploads/public/archive_0000003120_00/%E7%A7%8B%E7%94%B0%E7%9C%8C%E5%8C%BB%E7%99%82%E4%BF%9D%E5%81%A5%E7%A6%8F%E7%A5%89%E8%A8%88%E7%94%BB%EF%BC%8801+%E8%A1%A8%E7%B4%99%E3%83%BB%E7%9B%AE%E6%AC%A1%E3%83%BB%E7%B7%8F%E8%AB%96%E3%83%BB%E5%9C%B0%E5%9F%9F%E5%8C%BB%E7%99%82%E6%8F%90%E4%BE%9B%E4%BD%93%E5%88%B6%EF%BC%89.pdf"),
        ("akita_02_5shippei.pdf", "秋田県医療保健福祉計画 分割2（5疾病）",
         "https://www.pref.akita.lg.jp/uploads/public/archive_0000003120_00/%E7%A7%8B%E7%94%B0%E7%9C%8C%E5%8C%BB%E7%99%82%E4%BF%9D%E5%81%A5%E7%A6%8F%E7%A5%89%E8%A8%88%E7%94%BB%EF%BC%8802+%EF%BC%95%E7%96%BE%E7%97%85%EF%BC%89.pdf"),
        ("akita_03_6jigyou.pdf", "秋田県医療保健福祉計画 分割3（6事業等）",
         "https://www.pref.akita.lg.jp/uploads/public/archive_0000003120_00/%E7%A7%8B%E7%94%B0%E7%9C%8C%E5%8C%BB%E7%99%82%E4%BF%9D%E5%81%A5%E7%A6%8F%E7%A5%89%E8%A8%88%E7%94%BB%EF%BC%8803+%EF%BC%96%E4%BA%8B%E6%A5%AD%E7%AD%89%EF%BC%89.pdf"),
        ("akita_04_sonota.pdf", "秋田県医療保健福祉計画 分割4（その他・人材確保等）",
         "https://www.pref.akita.lg.jp/uploads/public/archive_0000003120_00/%E7%A7%8B%E7%94%B0%E7%9C%8C%E5%8C%BB%E7%99%82%E4%BF%9D%E5%81%A5%E7%A6%8F%E7%A5%89%E8%A8%88%E7%94%BB%EF%BC%8804+%E3%81%9D%E3%81%AE%E4%BB%96%E3%81%AE%E5%8C%BB%E7%99%82%E3%83%BB%E4%BA%BA%E6%9D%90%E7%A2%BA%E4%BF%9D%E7%AD%89%EF%BC%89.pdf"),
    ],
    6: [  # 山形県
        ("yamagata_zenbun.pdf", "第8次山形県保健医療計画 全体版",
         "https://www.pref.yamagata.jp/documents/8266/8jihontai.pdf"),
    ],
    7: [  # 福島県
        ("fukushima_zenbun.pdf", "第8次福島県医療計画 全体版",
         "https://www.pref.fukushima.lg.jp/uploaded/attachment/624113.pdf"),
    ],
    8: [  # 茨城県
        ("ibaraki_soron1.pdf", "総論第1章 計画の基本的な考え方",
         "https://www.pref.ibaraki.jp/hokenfukushi/iryo/keikaku/koso/health-med-plan/documents/soron1.pdf"),
        ("ibaraki_soron2.pdf", "総論第2章 現在の保健医療の状況",
         "https://www.pref.ibaraki.jp/hokenfukushi/iryo/keikaku/koso/health-med-plan/documents/soron2.pdf"),
        ("ibaraki_soron3.pdf", "総論第3章 将来の保健医療の状況",
         "https://www.pref.ibaraki.jp/hokenfukushi/iryo/keikaku/koso/health-med-plan/documents/soron3.pdf"),
        ("ibaraki_soron4.pdf", "総論第4章 保健医療圏と基準病床数",
         "https://www.pref.ibaraki.jp/hokenfukushi/iryo/keikaku/koso/health-med-plan/documents/soron4.pdf"),
        ("ibaraki_kakuron11.pdf", "各論第1章 5疾病・6事業（前半）",
         "https://www.pref.ibaraki.jp/hokenfukushi/iryo/keikaku/koso/health-med-plan/documents/kakuron11.pdf"),
        ("ibaraki_kakuron12.pdf", "各論第1章 5疾病・6事業（後半）",
         "https://www.pref.ibaraki.jp/hokenfukushi/iryo/keikaku/koso/health-med-plan/documents/kakuron12.pdf"),
        ("ibaraki_kakuron13.pdf", "各論第1章 在宅医療等",
         "https://www.pref.ibaraki.jp/hokenfukushi/iryo/keikaku/koso/health-med-plan/documents/kakuron13.pdf"),
        ("ibaraki_kakuron20.pdf", "各論第2章 健康でいきいきと生活し活躍できる環境づくり",
         "https://www.pref.ibaraki.jp/hokenfukushi/iryo/keikaku/koso/health-med-plan/documents/kakuron20.pdf"),
        ("ibaraki_kakuron30.pdf", "各論第3章 健康で安全な生活を支える取組の推進",
         "https://www.pref.ibaraki.jp/hokenfukushi/iryo/keikaku/koso/health-med-plan/documents/kakuron30.pdf"),
        ("ibaraki_kakuron40.pdf", "各論第4章 地域医療構想",
         "https://www.pref.ibaraki.jp/hokenfukushi/iryo/keikaku/koso/health-med-plan/documents/kakuron40.pdf"),
        ("ibaraki_kakuron50.pdf", "各論第5章 外来医療に係る医療提供体制の確保",
         "https://www.pref.ibaraki.jp/hokenfukushi/iryo/keikaku/koso/health-med-plan/documents/kakuron50.pdf"),
        ("ibaraki_kakuron60.pdf", "各論第6章 計画の推進体制と評価",
         "https://www.pref.ibaraki.jp/hokenfukushi/iryo/keikaku/koso/health-med-plan/documents/kakuron60.pdf"),
    ],
    9: [  # 栃木県
        ("tochigi_ch1.pdf", "第1章 保健医療計画の基本的な事項",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/02_hokeniryoukeikaku8_1.pdf"),
        ("tochigi_ch2.pdf", "第2章 栃木県の保健医療の現状",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/03_hokeniryoukeikaku8_2.pdf"),
        ("tochigi_ch3.pdf", "第3章 保健医療圏と基準病床数",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/04_hokeniryoukeikaku8_3.pdf"),
        ("tochigi_ch4.pdf", "第4章 良質で効率的な医療の確保",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/05_hokeniryoukeikaku8_4.pdf"),
        ("tochigi_ch5_1.pdf", "第5章 5疾病（がん・脳卒中・心筋梗塞）",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/06_hokeniryoukeikaku8_5_1.pdf"),
        ("tochigi_ch5_2.pdf", "第5章 5疾病（糖尿病・精神疾患）",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/06_hokeniryoukeikaku8_5_2.pdf"),
        ("tochigi_ch5_3.pdf", "第5章 6事業（救急・災害・感染症）",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/07_hokeniryoukeikaku8_5_3.pdf"),
        ("tochigi_ch5_4.pdf", "第5章 6事業（へき地・周産期・小児医療）",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/07_hokeniryoukeikaku8_5_4.pdf"),
        ("tochigi_ch5_5.pdf", "第5章 在宅医療",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/08_hokeniryoukeikaku8_5_5.pdf"),
        ("tochigi_ch6.pdf", "第6章 地域医療構想の取組",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/09_hokeniryoukeikaku8_6.pdf"),
        ("tochigi_ch7.pdf", "第7章 外来医療計画の取組",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/10_hokeniryoukeikaku8_7.pdf"),
        ("tochigi_ch8.pdf", "第8章 各分野の医療体制の充実",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/11_hokeniryoukeikaku8_8.pdf"),
        ("tochigi_ch9.pdf", "第9章 保健・医療・介護・福祉の総合的な取組",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/12_hokeniryoukeikaku8_9.pdf"),
        ("tochigi_ch10.pdf", "第10章 人材確保・育成",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/13_hokeniryoukeikaku8_10.pdf"),
        ("tochigi_ch11.pdf", "第11章 保健・医療・介護・福祉の連携",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/14_hokeniryoukeikaku8_11.pdf"),
        ("tochigi_shiryou.pdf", "資料編",
         "https://www.pref.tochigi.lg.jp/e02/pref/keikaku/bumon/documents/15_hokeniryoukeikaku8_shiryouhen.pdf"),
    ],
    10: [  # 群馬県（第9次）
        ("gunma_zenbun.pdf", "第9次群馬県保健医療計画",
         "https://www.pref.gunma.jp/uploaded/attachment/625708.pdf"),
        ("gunma_bessatsu.pdf", "第9次群馬県保健医療計画（別冊）",
         "https://www.pref.gunma.jp/uploaded/attachment/662708.pdf"),
    ],
    15: [  # 新潟県
        ("niigata_zenbun.pdf", "第8次新潟県地域保健医療計画",
         "https://www.pref.niigata.lg.jp/uploaded/attachment/476440.pdf"),
    ],
    16: [  # 富山県
        ("toyama_zenbun.pdf", "富山県医療計画（2024年3月改定版）",
         "https://www.pref.toyama.jp/documents/39876/iryokeikaku.pdf"),
    ],
    17: [  # 石川県
        ("ishikawa_zenbun.pdf", "第8次石川県医療計画（全体版）",
         "https://www.pref.ishikawa.lg.jp/iryou/support/iryoukeikaku/documents/dai8ji_iryokeikaku_zentai_260108.pdf"),
    ],
    18: [  # 福井県
        ("fukui_zenbun.pdf", "第8次福井県医療計画（全体版）",
         "https://www.pref.fukui.lg.jp/doc/iryou/iryoujouhou/8ji-iryoukeikaku_d/fil/008jiiryoukeikaku.pdf"),
    ],
    19: [  # 山梨県
        ("yamanashi_ch1.pdf", "第8次山梨県地域保健医療計画 第1章 基本的事項",
         "https://www.pref.yamanashi.jp/documents/1600/1_kihontekijikou.pdf"),
        ("yamanashi_ch2.pdf", "第8次山梨県地域保健医療計画 第2章 保健・医療提供体制の状況",
         "https://www.pref.yamanashi.jp/documents/1600/2_hokenniryouteikyoutaiseinojoukyou.pdf"),
        ("yamanashi_ch3.pdf", "第8次山梨県地域保健医療計画 第3章 人材確保と資質の向上",
         "https://www.pref.yamanashi.jp/documents/1600/3_jinzainokakuhotoshishitsunokoujou.pdf"),
        ("yamanashi_ch4.pdf", "第8次山梨県地域保健医療計画 第4章 地域医療提供体制の整備",
         "https://www.pref.yamanashi.jp/documents/1600/4_tiikiiryouteikyoutaiseinoseibi.pdf"),
        ("yamanashi_shiryou.pdf", "第8次山梨県地域保健医療計画 資料編",
         "https://www.pref.yamanashi.jp/documents/1600/9_shiryouhenn.pdf"),
    ],
    20: [  # 長野県
        ("nagano_hen1.pdf", "第3期信州保健医療総合計画 第1編",
         "https://www.pref.nagano.lg.jp/kenko-fukushi/kenko/iryo/shisaku/documents/1hen.pdf"),
        ("nagano_hen2.pdf", "第3期信州保健医療総合計画 第2編",
         "https://www.pref.nagano.lg.jp/kenko-fukushi/kenko/iryo/shisaku/documents/2hen.pdf"),
        ("nagano_hen3.pdf", "第3期信州保健医療総合計画 第3編",
         "https://www.pref.nagano.lg.jp/kenko-fukushi/kenko/iryo/shisaku/documents/3hen.pdf"),
        ("nagano_hen4.pdf", "第3期信州保健医療総合計画 第4編",
         "https://www.pref.nagano.lg.jp/kenko-fukushi/kenko/iryo/shisaku/documents/4hen.pdf"),
        ("nagano_hen5.pdf", "第3期信州保健医療総合計画 第5編",
         "https://www.pref.nagano.lg.jp/kenko-fukushi/kenko/iryo/shisaku/documents/5hen.pdf"),
        ("nagano_hen6.pdf", "第3期信州保健医療総合計画 第6編",
         "https://www.pref.nagano.lg.jp/kenko-fukushi/kenko/iryo/shisaku/documents/6hen.pdf"),
        ("nagano_hen7.pdf", "第3期信州保健医療総合計画 第7編",
         "https://www.pref.nagano.lg.jp/kenko-fukushi/kenko/iryo/shisaku/documents/7hen.pdf"),
        ("nagano_hen8.pdf", "第3期信州保健医療総合計画 第8編",
         "https://www.pref.nagano.lg.jp/kenko-fukushi/kenko/iryo/shisaku/documents/8hen.pdf"),
        ("nagano_hen9_1.pdf", "第3期信州保健医療総合計画 第9編（前半）",
         "https://www.pref.nagano.lg.jp/kenko-fukushi/kenko/iryo/shisaku/documents/9henzenhan.pdf"),
        ("nagano_hen9_2.pdf", "第3期信州保健医療総合計画 第9編（後半）",
         "https://www.pref.nagano.lg.jp/kenko-fukushi/kenko/iryo/shisaku/documents/9henkouhan.pdf"),
        ("nagano_shiryou.pdf", "第3期信州保健医療総合計画 資料編",
         "https://www.pref.nagano.lg.jp/kenko-fukushi/kenko/iryo/shisaku/documents/siryouhen.pdf"),
    ],
    21: [  # 岐阜県
        ("gifu_zenbun.pdf", "第8期岐阜県保健医療計画（本編）",
         "https://www.pref.gifu.lg.jp/uploaded/attachment/487880.pdf"),
    ],
    22: [  # 静岡県
        ("shizuoka_zenbun.pdf", "第9次静岡県保健医療計画（全県版・一括）",
         "https://www.pref.shizuoka.jp/_res/projects/default_project/_page_/001/054/250/000ikkatuinsatuyou.pdf"),
    ],
    24: [  # 三重県
        ("mie_zenbun.pdf", "第8次三重県医療計画（本冊一括）",
         "https://www.pref.mie.lg.jp/common/content/001149127.pdf"),
    ],
    25: [  # 滋賀県
        ("shiga_zenbun.pdf", "滋賀県保健医療計画（第8次・令和6年3月改定）",
         "https://www.pref.shiga.lg.jp/file/attachment/5450379.pdf"),
    ],
    26: [  # 京都府
        ("kyoto_honpen.pdf", "京都府保健医療計画（令和6年度〜令和11年度）本編",
         "https://www.pref.kyoto.jp/hofukuki/news/documents/honpen.pdf"),
    ],
    29: [  # 奈良県
        ("nara_gaiyou.pdf", "奈良県保健医療計画（第8次）概要版",
         "https://www.pref.nara.lg.jp/documents/11810/gaiyou.pdf"),
        ("nara_ch1.pdf", "奈良県保健医療計画 第1章 基本的事項",
         "https://www.pref.nara.lg.jp/documents/11810/01_kihontekizikou.pdf"),
        ("nara_ch2.pdf", "奈良県保健医療計画 第2章 奈良県の現状",
         "https://www.pref.nara.lg.jp/documents/11810/02_genzyou.pdf"),
        ("nara_ch3.pdf", "奈良県保健医療計画 第3章 保健医療圏・基準病床数",
         "https://www.pref.nara.lg.jp/documents/11810/03_hokeniryoukenn.pdf"),
        ("nara_ch4.pdf", "奈良県保健医療計画 第4章 医療機能の分担と連携",
         "https://www.pref.nara.lg.jp/documents/11810/04_iryoukinou.pdf"),
        ("nara_ch5_gan.pdf", "奈良県保健医療計画 第5章 がん",
         "https://www.pref.nara.lg.jp/documents/11810/05-1_gan.pdf"),
        ("nara_ch6.pdf", "奈良県保健医療計画 第6章 外来医療",
         "https://www.pref.nara.lg.jp/documents/11810/06_gairai.pdf"),
        ("nara_ch11.pdf", "奈良県保健医療計画 第11章 推進体制",
         "https://www.pref.nara.lg.jp/documents/11810/11_suisinntaisei.pdf"),
    ],
    30: [  # 和歌山県
        ("wakayama_zentai.pdf", "第八次和歌山県保健医療計画 全体版",
         "https://www.pref.wakayama.lg.jp/prefg/050100/iryokeikaku/keikaku_d/fil/zentai.pdf"),
    ],
    31: [  # 鳥取県
        ("tottori_01_hyoushi.pdf", "表紙・目次・第1章〜第2章",
         "https://www.pref.tottori.lg.jp/secure/1249330/01_hyoushi_.pdf"),
        ("tottori_02_iryouken.pdf", "保健医療圏・基準病床数",
         "https://www.pref.tottori.lg.jp/secure/1249330/02_hokeniryou-kizyunbyousyou_.pdf"),
        ("tottori_03_5shippei.pdf", "5疾病",
         "https://www.pref.tottori.lg.jp/secure/1249330/R7_03_5shippei_.pdf"),
        ("tottori_04_7jigyou.pdf", "7事業",
         "https://www.pref.tottori.lg.jp/secure/1249330/R7_04_7jigyou_.pdf"),
        ("tottori_05_juujisha.pdf", "医療従事者の確保と資質の向上",
         "https://www.pref.tottori.lg.jp/secure/1249330/R7_05_iryouzyuzisya-kakuho_.pdf"),
        ("tottori_06_kadaibetsu.pdf", "課題別対策",
         "https://www.pref.tottori.lg.jp/secure/1249330/R7_06_kadaibetutaisaku_.pdf"),
        ("tottori_07_gairai.pdf", "外来医療計画",
         "https://www.pref.tottori.lg.jp/secure/1249330/07_gairaiiryoukeikaku_.pdf"),
        ("tottori_08_kenko.pdf", "健康づくり",
         "https://www.pref.tottori.lg.jp/secure/1249330/R7_08_kenkoudukuri_.pdf"),
        ("tottori_09_tekiseika.pdf", "医療費適正化",
         "https://www.pref.tottori.lg.jp/secure/1249330/R7_09_iryouhitekiseika_.pdf"),
        ("tottori_10_toubu.pdf", "東部保健医療圏",
         "https://www.pref.tottori.lg.jp/secure/1249330/R7_10_toubuhokeniryoukeikaku.pdf"),
        ("tottori_11_chubu.pdf", "中部保健医療圏",
         "https://www.pref.tottori.lg.jp/secure/1249330/R7_11_chubuhokeniryoukeikaku.pdf"),
        ("tottori_12_seibu.pdf", "西部保健医療圏",
         "https://www.pref.tottori.lg.jp/secure/1249330/R7_12_seibuhokeniryoukeikaku.pdf"),
    ],
    32: [  # 島根県
        ("shimane_all.pdf", "島根県保健医療計画 全体版",
         "https://www.pref.shimane.lg.jp/medical/kenko/iryo/shimaneno_iryo/hokenniryoukeikaku/index.data/hokeniryokeikakuall.pdf"),
    ],
    33: [  # 岡山県（第9次）
        ("okayama_ch1.pdf", "第1章 計画の基本的事項",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683328_misc.pdf"),
        ("okayama_ch2.pdf", "第2章 岡山県の保健医療の現状",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683344_misc.pdf"),
        ("okayama_ch3.pdf", "第3章 保健医療圏",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683345_misc.pdf"),
        ("okayama_ch4.pdf", "第4章 基準病床数",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683346_misc.pdf"),
        ("okayama_ch5.pdf", "第5章 地域医療構想",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683347_misc.pdf"),
        ("okayama_ch6.pdf", "第6章 医療提供体制の整備",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683358_misc.pdf"),
        ("okayama_ch7.pdf", "第7章 疾病又は事業ごとの医療連携体制の構築",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683359_misc.pdf"),
        ("okayama_ch8.pdf", "第8章 地域保健医療・生活衛生対策の推進",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683370_misc.pdf"),
        ("okayama_ch9.pdf", "第9章 保健・医療・介護の総合的な取組の推進",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683371_misc.pdf"),
        ("okayama_ch10.pdf", "第10章 保健医療従事者の確保と資質の向上",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683372_misc.pdf"),
        ("okayama_ch12.pdf", "第12章 計画の推進体制と評価",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683424_misc.pdf"),
        ("okayama_kennantoubu.pdf", "県南東部保健医療圏",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683384_misc.pdf"),
        ("okayama_kennanseibu.pdf", "県南西部保健医療圏",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683385_misc.pdf"),
        ("okayama_takahashi.pdf", "高梁・新見保健医療圏",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683386_misc.pdf"),
        ("okayama_maniwa.pdf", "真庭保健医療圏",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683392_misc.pdf"),
        ("okayama_tsuyama.pdf", "津山・英田保健医療圏",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683408_misc.pdf"),
        ("okayama_sankou.pdf", "参考資料",
         "https://www.pref.okayama.jp/uploaded/life/908918_8683428_misc.pdf"),
    ],
    35: [  # 山口県
        ("yamaguchi_hyoushi.pdf", "表紙・はじめに・目次",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176979.pdf"),
        ("yamaguchi_pt1.pdf", "第1部 基本的事項",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176980.pdf"),
        ("yamaguchi_kousou.pdf", "第1編 地域医療構想推進",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176981.pdf"),
        ("yamaguchi_gan.pdf", "第2編第1章 がん",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176982.pdf"),
        ("yamaguchi_nousotchuu.pdf", "第2編第2章 脳卒中・心筋梗塞等",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176983.pdf"),
        ("yamaguchi_tounyou.pdf", "第2編第3章 糖尿病",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176984.pdf"),
        ("yamaguchi_seishin.pdf", "第2編第4章 精神疾患",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176985.pdf"),
        ("yamaguchi_kyukyu.pdf", "第3編第1章 救急医療",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176986.pdf"),
        ("yamaguchi_saigai.pdf", "第3編第2章 災害医療",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176987.pdf"),
        ("yamaguchi_kansen.pdf", "第3編第3章 新興感染症医療",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176988.pdf"),
        ("yamaguchi_hekichi.pdf", "第3編第4章 へき地医療",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176989.pdf"),
        ("yamaguchi_shusanki.pdf", "第3編第5章 周産期医療",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176990.pdf"),
        ("yamaguchi_shouni.pdf", "第3編第6章 小児医療",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176991.pdf"),
        ("yamaguchi_zaitaku.pdf", "第4編 在宅医療",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176992.pdf"),
        ("yamaguchi_gairai.pdf", "第5編 外来医療",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176993.pdf"),
        ("yamaguchi_bunyabetsu.pdf", "第6編 分野別対策",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176995.pdf"),
        ("yamaguchi_anzen.pdf", "第7編 医療安全・向上",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176996.pdf"),
        ("yamaguchi_jinzai.pdf", "第3部 人材確保と資質向上",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176997.pdf"),
        ("yamaguchi_sankou.pdf", "数値目標・参考資料",
         "https://www.pref.yamaguchi.lg.jp/uploaded/attachment/176999.pdf"),
    ],
    36: [  # 徳島県
        ("tokushima_hontai.pdf", "第8次徳島県保健医療計画（本体）",
         "https://www.pref.tokushima.lg.jp/file/attachment/914006.pdf"),
        ("tokushima_shiryou.pdf", "第8次徳島県保健医療計画（資料編）",
         "https://www.pref.tokushima.lg.jp/file/attachment/917074.pdf"),
    ],
    37: [  # 香川県
        ("kagawa_ch1_3.pdf", "第1章・第2章・第3章",
         "https://www.pref.kagawa.lg.jp/documents/11649/dai8ji1-3.pdf"),
        ("kagawa_ch4.pdf", "第4章 医師確保計画",
         "https://www.pref.kagawa.lg.jp/documents/11649/dai8ji4.pdf"),
        ("kagawa_ch5.pdf", "第5章",
         "https://www.pref.kagawa.lg.jp/documents/11649/dai8ji5.pdf"),
        ("kagawa_ch6.pdf", "第6章 外来医療計画",
         "https://www.pref.kagawa.lg.jp/documents/11649/dai8ji6.pdf"),
        ("kagawa_ch7_8.pdf", "第7章・第8章",
         "https://www.pref.kagawa.lg.jp/documents/11649/dai8ji7-8.pdf"),
        ("kagawa_ch9_10.pdf", "第9章・第10章",
         "https://www.pref.kagawa.lg.jp/documents/11649/dai8ji9-10.pdf"),
    ],
    38: [  # 愛媛県
        ("ehime_ch01.pdf", "第1章 計画の基本的事項",
         "https://www.pref.ehime.jp/uploaded/attachment/110828.pdf"),
        ("ehime_ch02.pdf", "第2章 保健医療の現状",
         "https://www.pref.ehime.jp/uploaded/attachment/110829.pdf"),
        ("ehime_ch03.pdf", "第3章 保健医療圏の設定と病床の整備",
         "https://www.pref.ehime.jp/uploaded/attachment/110830.pdf"),
        ("ehime_ch04_01.pdf", "第4章-1 基本的考え方",
         "https://www.pref.ehime.jp/uploaded/attachment/110831.pdf"),
        ("ehime_ch04_tounyou.pdf", "第4章 糖尿病",
         "https://www.pref.ehime.jp/uploaded/attachment/110832.pdf"),
        ("ehime_ch04_seishin.pdf", "第4章 精神疾患",
         "https://www.pref.ehime.jp/uploaded/attachment/110833.pdf"),
        ("ehime_ch04_kyukyu.pdf", "第4章 救急医療",
         "https://www.pref.ehime.jp/uploaded/attachment/110834.pdf"),
        ("ehime_ch04_saigai.pdf", "第4章 災害医療及び原子力災害医療",
         "https://www.pref.ehime.jp/uploaded/attachment/110835.pdf"),
        ("ehime_ch04_hekichi.pdf", "第4章 へき地医療",
         "https://www.pref.ehime.jp/uploaded/attachment/110836.pdf"),
        ("ehime_ch04_shusanki.pdf", "第4章 周産期医療",
         "https://www.pref.ehime.jp/uploaded/attachment/110837.pdf"),
        ("ehime_ch04_shouni.pdf", "第4章 小児医療",
         "https://www.pref.ehime.jp/uploaded/attachment/110838.pdf"),
        ("ehime_ch04_zaitaku.pdf", "第4章 在宅医療",
         "https://www.pref.ehime.jp/uploaded/attachment/110839.pdf"),
        ("ehime_ch04_hyoka.pdf", "第4章 5疾病6事業及び在宅医療に係る評価等",
         "https://www.pref.ehime.jp/uploaded/attachment/110840.pdf"),
        ("ehime_ch04_03_08.pdf", "第4章 3~8節",
         "https://www.pref.ehime.jp/uploaded/attachment/110841.pdf"),
        ("ehime_ch05.pdf", "第5章 外来医療",
         "https://www.pref.ehime.jp/uploaded/attachment/110842.pdf"),
        ("ehime_ch06.pdf", "第6章 医師の確保",
         "https://www.pref.ehime.jp/uploaded/attachment/110843.pdf"),
        ("ehime_ch07.pdf", "第7章 薬剤師の確保",
         "https://www.pref.ehime.jp/uploaded/attachment/110844.pdf"),
        ("ehime_ch08.pdf", "第8章 医療従事者の確保",
         "https://www.pref.ehime.jp/uploaded/attachment/110845.pdf"),
        ("ehime_ch09.pdf", "第9章 保健・医療・介護・福祉の総合的な取組み",
         "https://www.pref.ehime.jp/uploaded/attachment/110846.pdf"),
        ("ehime_ch10.pdf", "第10章 健康危機管理体制の構築",
         "https://www.pref.ehime.jp/uploaded/attachment/110847.pdf"),
        ("ehime_ch11.pdf", "第11章 地域保健体制の整備",
         "https://www.pref.ehime.jp/uploaded/attachment/110848.pdf"),
        ("ehime_ch12.pdf", "第12章 地域医療構想",
         "https://www.pref.ehime.jp/uploaded/attachment/110849.pdf"),
    ],
    39: [  # 高知県
        ("kochi_zentai.pdf", "第8期高知県保健医療計画 全体版",
         "https://www.pref.kochi.lg.jp/doc/2024032600623/file_contents/file_2024722115246_1.pdf"),
    ],
    41: [  # 佐賀県
        ("saga_ch1_3.pdf", "第1章～第3章",
         "https://www.pref.saga.lg.jp/kiji003105828/3_105828_315322_up_i5lvm81j.pdf"),
        ("saga_ch4.pdf", "第4章",
         "https://www.pref.saga.lg.jp/kiji003105828/3_105828_315323_up_74lx3p1t.pdf"),
        ("saga_ch5.pdf", "第5章",
         "https://www.pref.saga.lg.jp/kiji003105828/3_105828_315324_up_qnchjuy5.pdf"),
        ("saga_ch6_10.pdf", "第6章～第10章",
         "https://www.pref.saga.lg.jp/kiji003105828/3_105828_315325_up_co6hr2rz.pdf"),
        ("saga_bessatsu.pdf", "別冊",
         "https://www.pref.saga.lg.jp/kiji003105828/3_105828_315643_up_m62qubba.pdf"),
    ],
    43: [  # 熊本県
        ("kumamoto_gaiyou.pdf", "第8次熊本県保健医療計画 概要",
         "https://www.pref.kumamoto.jp/uploaded/life/202905_529961_misc.pdf"),
        ("kumamoto_hyoushi.pdf", "表紙・目次",
         "https://www.pref.kumamoto.jp/uploaded/life/202905_529963_misc.pdf"),
        ("kumamoto_hen1.pdf", "第1編 基本構想",
         "https://www.pref.kumamoto.jp/uploaded/life/202905_529964_misc.pdf"),
        ("kumamoto_hen2_ch1.pdf", "第2編第1章 保健医療圏の設定と基準病床数",
         "https://www.pref.kumamoto.jp/uploaded/life/202905_529965_misc.pdf"),
        ("kumamoto_hen2_ch2.pdf", "第2編第2章 生涯を通じた健康づくり",
         "https://www.pref.kumamoto.jp/uploaded/life/202905_529966_misc.pdf"),
        ("kumamoto_hen2_ch3_1.pdf", "第2編第3章第1節 住民・患者の立場に立った保健医療施策",
         "https://www.pref.kumamoto.jp/uploaded/life/202905_529972_misc.pdf"),
        ("kumamoto_hen2_ch3_2.pdf", "第2編第3章第2節 疾病に応じた保健医療施策",
         "https://www.pref.kumamoto.jp/uploaded/life/202905_529973_misc.pdf"),
        ("kumamoto_hen2_ch3_3.pdf", "第2編第3章第3節 特定の課題に応じた保健医療施策",
         "https://www.pref.kumamoto.jp/uploaded/life/202905_529974_misc.pdf"),
        ("kumamoto_hen2_ch4.pdf", "第2編第4章 人材確保・育成",
         "https://www.pref.kumamoto.jp/uploaded/life/202905_529975_misc.pdf"),
        ("kumamoto_hen2_ch5.pdf", "第2編第5章 健康危機への対応",
         "https://www.pref.kumamoto.jp/uploaded/life/202905_529976_misc.pdf"),
        ("kumamoto_hen3.pdf", "第3編 圏域編",
         "https://www.pref.kumamoto.jp/uploaded/life/202905_529978_misc.pdf"),
        ("kumamoto_hen4.pdf", "第4編 計画の実現に向けて",
         "https://www.pref.kumamoto.jp/uploaded/life/202905_529980_misc.pdf"),
        ("kumamoto_sankou1.pdf", "参考資料1 ロジックモデル",
         "https://www.pref.kumamoto.jp/uploaded/life/202905_529982_misc.pdf"),
        ("kumamoto_sankou2.pdf", "参考資料2 指標一覧",
         "https://www.pref.kumamoto.jp/uploaded/life/202905_529983_misc.pdf"),
    ],
    44: [  # 大分県
        ("oita_zenbun.pdf", "第8次大分県医療計画（全体）",
         "https://www.pref.oita.jp/uploaded/life/2259226_4324351_misc.pdf"),
    ],
    45: [  # 宮崎県
        ("miyazaki_ch1.pdf", "第1章 総論",
         "https://www.pref.miyazaki.lg.jp/documents/87380/87380_20240327143150-1.pdf"),
        ("miyazaki_ch2.pdf", "第2章 地域の概況",
         "https://www.pref.miyazaki.lg.jp/documents/87380/87380_20240327143210-1.pdf"),
        ("miyazaki_ch3.pdf", "第3章 医療圏の設定と基準病床数",
         "https://www.pref.miyazaki.lg.jp/documents/87380/87380_20240327143229-1.pdf"),
        ("miyazaki_ch4.pdf", "第4章 医療提供体制の構築",
         "https://www.pref.miyazaki.lg.jp/documents/87380/87380_20250313091846-1.pdf"),
        ("miyazaki_ch5.pdf", "第5章 地域医療構想",
         "https://www.pref.miyazaki.lg.jp/documents/87380/87380_20240327143316-1.pdf"),
        ("miyazaki_ch6.pdf", "第6章 外来医療計画",
         "https://www.pref.miyazaki.lg.jp/documents/87380/87380_20240327143335-1.pdf"),
        ("miyazaki_ch7.pdf", "第7章 医療提供基盤の充実",
         "https://www.pref.miyazaki.lg.jp/documents/87380/87380_20240327143354-1.pdf"),
        ("miyazaki_ch8.pdf", "第8章 計画の推進等",
         "https://www.pref.miyazaki.lg.jp/documents/87380/87380_20240327143413-1.pdf"),
        ("miyazaki_sankou.pdf", "参考",
         "https://www.pref.miyazaki.lg.jp/documents/87380/87380_20240327143441-1.pdf"),
    ],
    46: [  # 鹿児島県
        ("kagoshima_gaiyou.pdf", "鹿児島県保健医療計画 概要",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328154122-1.pdf"),
        ("kagoshima_ch1_1.pdf", "第1章第1節 計画の策定",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328154223-1.pdf"),
        ("kagoshima_ch1_2.pdf", "第1章第2節 鹿児島県の概要",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328154248-1.pdf"),
        ("kagoshima_ch1_3.pdf", "第1章第3節 地域診断",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328154348-1.pdf"),
        ("kagoshima_ch2_1.pdf", "第2章第1節 保健医療圏の役割",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328154434-1.pdf"),
        ("kagoshima_ch2_2.pdf", "第2章第2節 二次保健医療圏の設定",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328154518-1.pdf"),
        ("kagoshima_ch2_3.pdf", "第2章第3節 基準病床数",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328154656-1.pdf"),
        ("kagoshima_ch3_1.pdf", "第3章第1節 健康の増進",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328154725-1.pdf"),
        ("kagoshima_ch3_2.pdf", "第3章第2節 保健対策の推進",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328154755-1.pdf"),
        ("kagoshima_ch3_3.pdf", "第3章第3節 疾病予防対策の推進",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328154825-1.pdf"),
        ("kagoshima_ch4_1.pdf", "第4章第1節 医療提供体制の整備",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328154910-1.pdf"),
        ("kagoshima_ch4_2.pdf", "第4章第2節 安全・安心な医療提供体制の整備",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328154935-1.pdf"),
        ("kagoshima_ch5_1.pdf", "第5章第1節 医療従事者の確保及び資質の向上",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328155017-1.pdf"),
        ("kagoshima_ch5_2.pdf", "第5章第2節 医療連携体制の構築",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328155043-1.pdf"),
        ("kagoshima_ch5_3.pdf", "第5章第3節 疾病別の医療連携体制",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328155114-1.pdf"),
        ("kagoshima_ch5_4_kyukyu.pdf", "第5章第4節 救急医療",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328165019-1.pdf"),
        ("kagoshima_ch5_4_saigai.pdf", "第5章第4節 災害医療",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328165042-1.pdf"),
        ("kagoshima_ch5_4_kansen.pdf", "第5章第4節 新興感染症発生・まん延時における医療",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328165114-1.pdf"),
        ("kagoshima_ch5_4_hekichi.pdf", "第5章第4節 離島・へき地医療",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328165146-1.pdf"),
        ("kagoshima_ch5_4_shusan.pdf", "第5章第4節 周産期医療",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328165218-1.pdf"),
        ("kagoshima_ch5_4_shouni.pdf", "第5章第4節 小児医療・小児救急医療",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328165241-1.pdf"),
        ("kagoshima_ch5_5.pdf", "第5章第5節 その他の医療を提供する体制の確保",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328155141-1.pdf"),
        ("kagoshima_ch6_1.pdf", "第6章第1節 介護サービス等の充実",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328155214-1.pdf"),
        ("kagoshima_ch6_2.pdf", "第6章第2節 在宅医療・人生の最終段階における医療の体制整備",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328155245-1.pdf"),
        ("kagoshima_ch7_1.pdf", "第7章第1節 地域医療提供体制の概要等",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328155457-1.pdf"),
        ("kagoshima_ch7_3.pdf", "第7章第3節 構想区域と病床の必要量",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328155549-1.pdf"),
        ("kagoshima_ch7_5.pdf", "第7章第5節 外来医療計画",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328155653-1.pdf"),
        ("kagoshima_ch10_2.pdf", "第10章第2節 数値目標の設定",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328161540-1.pdf"),
        ("kagoshima_ch11_2.pdf", "第11章第2節 各圏域の人口構造の変化の見通し及び医療連携体制",
         "https://www.pref.kagoshima.jp/ae01/kenko-fukushi/kenko-iryo/iryokeikaku/documents/111757_20240328161749-1.pdf"),
    ],
}

# --- DB・ディレクトリパス ---
HOME = Path.home()


def get_db_path(code):
    """都道府県コードからDBパスを返す"""
    if code == 12:  # 千葉
        return HOME / "chiba_pdf_db" / "chiba_iryo.db"
    elif code == 27:  # 大阪
        return HOME / "osaka_pdf_db" / "osaka_iryo.db"
    else:
        short = PREF_SHORT.get(code, f"pref{code:02d}")
        name = PREF_NAMES[code]
        dir_name = f"prefdb_{code:02d}_{name}"
        db_dir = HOME / dir_name
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir / f"{code:02d}_iryo.db"


def get_pdf_dir(code):
    """都道府県コードからPDF保存ディレクトリを返す"""
    db_path = get_db_path(code)
    pdf_dir = db_path.parent / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    return pdf_dir


def init_db(conn):
    """documents / pages / pages_fts テーブルを作成"""
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY,
            filename TEXT,
            title TEXT,
            total_pages INTEGER
        );
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY,
            doc_id INTEGER,
            page_num INTEGER,
            text TEXT,
            FOREIGN KEY(doc_id) REFERENCES documents(id)
        );
    """)
    # FTS5テーブルは既存チェック
    res = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pages_fts'"
    ).fetchone()
    if not res:
        cur.execute("""
            CREATE VIRTUAL TABLE pages_fts USING fts5(
                text,
                content='pages',
                content_rowid='id'
            );
        """)
    conn.commit()


def download_pdf(url, dest, sleep_sec=3):
    """PDFをダウンロード。既存ならスキップ。"""
    if dest.exists() and dest.stat().st_size > 0:
        print(f"    スキップ（既存 {dest.stat().st_size // 1024}KB）")
        return True
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=120, stream=True)
        r.raise_for_status()
        content = r.content
        dest.write_bytes(content)
        print(f"    ダウンロード完了 ({len(content) // 1024}KB)")
        time.sleep(sleep_sec)
        return True
    except Exception as e:
        print(f"    ダウンロードエラー: {e}")
        return False


def extract_and_store(conn, pdf_path, filename, title):
    """PDFからテキスト抽出しDBに格納"""
    cur = conn.cursor()

    # 既存チェック
    existing = cur.execute(
        "SELECT id FROM documents WHERE filename = ?", (filename,)
    ).fetchone()
    if existing:
        print(f"    DB既存（スキップ）: {filename}")
        return 0

    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            cur.execute(
                "INSERT INTO documents (filename, title, total_pages) VALUES (?,?,?)",
                (filename, title, total_pages),
            )
            doc_id = cur.lastrowid

            for page_num, page in enumerate(pdf.pages, 1):
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                cur.execute(
                    "INSERT INTO pages (doc_id, page_num, text) VALUES (?,?,?)",
                    (doc_id, page_num, text),
                )
                page_id = cur.lastrowid
                if text.strip():
                    cur.execute(
                        "INSERT INTO pages_fts (rowid, text) VALUES (?,?)",
                        (page_id, text),
                    )

            conn.commit()
            print(f"    DB格納完了 ({total_pages}ページ)")
            return total_pages
    except Exception as e:
        print(f"    抽出エラー: {e}")
        conn.rollback()
        return 0


def process_prefecture(code):
    """1つの都道府県を処理"""
    name = PREF_NAMES.get(code)
    if not name:
        print(f"不明な都道府県コード: {code}")
        return None

    pdfs = PREF_PDFS.get(code)
    if not pdfs:
        print(f"{name}({code:02d}): PDFのURL定義がありません")
        return None

    print(f"\n{'='*60}")
    print(f"  {name}（コード: {code:02d}）")
    print(f"{'='*60}")

    db_path = get_db_path(code)
    pdf_dir = get_pdf_dir(code)

    print(f"  DB: {db_path}")
    print(f"  PDF: {pdf_dir}")

    conn = sqlite3.connect(db_path)
    init_db(conn)

    total_docs = 0
    total_pages = 0
    errors = []

    for i, (filename, title, url) in enumerate(pdfs, 1):
        print(f"  [{i:02d}/{len(pdfs)}] {title}")
        pdf_path = pdf_dir / filename

        if not download_pdf(url, pdf_path):
            errors.append(filename)
            continue

        pages = extract_and_store(conn, pdf_path, filename, title)
        if pages > 0:
            total_docs += 1
            total_pages += pages

    # 既存のものもカウント
    cur = conn.cursor()
    db_docs = cur.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    db_pages = cur.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    conn.close()

    result = {
        "code": code,
        "name": name,
        "db_path": str(db_path),
        "new_docs": total_docs,
        "new_pages": total_pages,
        "total_docs": db_docs,
        "total_pages": db_pages,
        "errors": errors,
    }

    print(f"\n  結果: {db_docs}文書 / {db_pages}ページ（DB合計）")
    if errors:
        print(f"  エラー: {errors}")

    return result


def main():
    parser = argparse.ArgumentParser(description="都道府県 地域医療計画PDF DB化")
    parser.add_argument("--code", type=int, nargs="+", help="都道府県コード（複数可）")
    parser.add_argument("--all10", action="store_true", help="主要10都道府県を一括処理")
    args = parser.parse_args()

    if args.all10:
        codes = [13, 14, 11, 23, 40, 1, 4, 34, 28, 47]
    elif args.code:
        codes = args.code
    else:
        parser.print_help()
        sys.exit(1)

    results = []
    for code in codes:
        result = process_prefecture(code)
        if result:
            results.append(result)

    # サマリー
    print(f"\n{'='*60}")
    print("  サマリー")
    print(f"{'='*60}")
    print(f"{'都道府県':>10} {'文書数':>6} {'ページ数':>8}  DB")
    print("-" * 60)
    for r in results:
        status = "⚠" if r["errors"] else "✓"
        print(f"{status} {r['name']:>8} {r['total_docs']:>6} {r['total_pages']:>8}  {r['db_path']}")
    print("-" * 60)
    total_d = sum(r["total_docs"] for r in results)
    total_p = sum(r["total_pages"] for r in results)
    print(f"  {'合計':>8} {total_d:>6} {total_p:>8}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
KSレコードパーサー: １４．騎手マスタ

Source: 公式JV-Data仕様書 Ver.4.9.0.1 「１４．騎手マスタ」
"""

from typing import Dict, Optional
from src.utils.logger import get_logger


class KSParser:
    """
    KSレコードパーサー

    １４．騎手マスタ
    レコード長: 4173 bytes
    VBテーブル名: KISYU
    """

    RECORD_TYPE = "KS"
    RECORD_LENGTH = 4173

    def __init__(self):
        self.logger = get_logger(__name__)

    @staticmethod
    def decode_field(data: bytes) -> str:
        """バイトデータをデコードして文字列に変換"""
        try:
            # cp932でデコード、空白を除去
            return data.decode("cp932", errors="replace").strip()
        except Exception:
            return ""

    def parse(self, data: bytes) -> Optional[Dict[str, str]]:
        """
        KSレコードをパースしてフィールド辞書を返す

        Args:
            data: パース対象のバイトデータ

        Returns:
            フィールド名をキーとした辞書、エラー時はNone
        """
        try:
            # レコード長チェック
            if len(data) < self.RECORD_LENGTH:
                self.logger.warning(
                    f"KSレコード長不足: expected={self.RECORD_LENGTH}, actual={len(data)}"
                )
                # return None  # 短いレコードも許容する場合はコメントアウト

            # フィールド抽出
            result = {}

            # 1. レコード種別ID (位置:1, 長さ:2)
            result["RecordSpec"] = self.decode_field(data[0:2])

            # 2. データ区分 (位置:3, 長さ:1)
            result["DataKubun"] = self.decode_field(data[2:3])

            # 3. データ作成年月日 (位置:4, 長さ:8)
            result["MakeDate"] = self.decode_field(data[3:11])

            # 4. 騎手コード (位置:12, 長さ:5)
            result["KisyuCode"] = self.decode_field(data[11:16])

            # 5. 騎手抹消区分 (位置:17, 長さ:1)
            result["DelKubun"] = self.decode_field(data[16:17])

            # 6. 騎手免許交付年月日 (位置:18, 長さ:8)
            result["IssueDate"] = self.decode_field(data[17:25])

            # 7. 騎手免許抹消年月日 (位置:26, 長さ:8)
            result["DelDate"] = self.decode_field(data[25:33])

            # 8. 生年月日 (位置:34, 長さ:8)
            result["BirthDate"] = self.decode_field(data[33:41])

            # 9. 騎手名 (位置:42, 長さ:34)
            result["KisyuName"] = self.decode_field(data[41:75])

            # 10. 予備 (位置:76, 長さ:34)
            result["reserved"] = self.decode_field(data[75:109])

            # 11. 騎手名半角ｶﾅ (位置:110, 長さ:30)
            result["KisyuNameKana"] = self.decode_field(data[109:139])

            # 12. 騎手名略称 (位置:140, 長さ:8)
            result["KisyuRyakusyo"] = self.decode_field(data[139:147])

            # 13. 騎手名欧字 (位置:148, 長さ:80)
            result["KisyuNameEng"] = self.decode_field(data[147:227])

            # 14. 性別区分 (位置:228, 長さ:1)
            result["SexCD"] = self.decode_field(data[227:228])

            # 15. 騎乗資格コード (位置:229, 長さ:1)
            result["SikakuCD"] = self.decode_field(data[228:229])

            # 16. 騎手見習コード (位置:230, 長さ:1)
            result["MinaraiCD"] = self.decode_field(data[229:230])

            # 17. 騎手東西所属コード (位置:231, 長さ:1)
            result["TozaiCD"] = self.decode_field(data[230:231])

            # 18. 招待地域名 (位置:232, 長さ:20)
            result["Syotai"] = self.decode_field(data[231:251])

            # 19. 所属調教師コード (位置:252, 長さ:5)
            result["ChokyosiCode"] = self.decode_field(data[251:256])

            # 20. 所属調教師名略称 (位置:257, 長さ:8)
            result["ChokyosiRyakusyo"] = self.decode_field(data[256:264])

            # 21. <初騎乗情報> (位置:265, 長さ:0)
            # This is a section header with length 0, no field assigned
            # 22. 　　年月日場回日R (位置:265, 長さ:16)
            result["HatuKiJyo1Hatukijyoid"] = self.decode_field(data[264:280])

            # 23. 　　出走頭数 (位置:281, 長さ:2)
            result["HatuKiJyo1SyussoTosu"] = self.decode_field(data[280:282])

            # 24. 　　血統登録番号 (位置:283, 長さ:10)
            result["HatuKiJyo1KettoNum"] = self.decode_field(data[282:292])

            # 25. 　　馬名 (位置:293, 長さ:36)
            result["HatuKiJyo1Bamei"] = self.decode_field(data[292:328])

            # 26. 　　確定着順 (位置:329, 長さ:2)
            result["HatuKiJyo1KakuteiJyuni"] = self.decode_field(data[328:330])

            # 27. 　　異常区分コード (位置:331, 長さ:1)
            result["HatuKiJyo1IJyoCD"] = self.decode_field(data[330:331])

            # 21-2. <初騎乗情報> 障害 年月日場回日R (位置:332, 長さ:16)
            result["HatuKiJyo2Hatukijyoid"] = self.decode_field(data[331:347])

            # 21-2. <初騎乗情報> 障害 出走頭数 (位置:348, 長さ:2)
            result["HatuKiJyo2SyussoTosu"] = self.decode_field(data[347:349])

            # 21-2. <初騎乗情報> 障害 血統登録番号 (位置:350, 長さ:10)
            result["HatuKiJyo2KettoNum"] = self.decode_field(data[349:359])

            # 21-2. <初騎乗情報> 障害 馬名 (位置:360, 長さ:36)
            result["HatuKiJyo2Bamei"] = self.decode_field(data[359:395])

            # 21-2. <初騎乗情報> 障害 確定着順 (位置:396, 長さ:2)
            result["HatuKiJyo2KakuteiJyuni"] = self.decode_field(data[395:397])

            # 21-2. <初騎乗情報> 障害 異常区分コード (位置:398, 長さ:1)
            result["HatuKiJyo2IJyoCD"] = self.decode_field(data[397:398])

            # 22-1. <初勝利情報> 平地 年月日場回日R (位置:399, 長さ:16)
            result["HatuSyori1Hatusyoriid"] = self.decode_field(data[398:414])

            # 22-1. <初勝利情報> 平地 出走頭数 (位置:415, 長さ:2)
            result["HatuSyori1SyussoTosu"] = self.decode_field(data[414:416])

            # 22-1. <初勝利情報> 平地 血統登録番号 (位置:417, 長さ:10)
            result["HatuSyori1KettoNum"] = self.decode_field(data[416:426])

            # 22-1. <初勝利情報> 平地 馬名 (位置:427, 長さ:36)
            result["HatuSyori1Bamei"] = self.decode_field(data[426:462])

            # 22-2. <初勝利情報> 障害 年月日場回日R (位置:463, 長さ:16)
            result["HatuSyori2Hatusyoriid"] = self.decode_field(data[462:478])

            # 22-2. <初勝利情報> 障害 出走頭数 (位置:479, 長さ:2)
            result["HatuSyori2SyussoTosu"] = self.decode_field(data[478:480])

            # 22-2. <初勝利情報> 障害 血統登録番号 (位置:481, 長さ:10)
            result["HatuSyori2KettoNum"] = self.decode_field(data[480:490])

            # 22-2. <初勝利情報> 障害 馬名 (位置:491, 長さ:36)
            result["HatuSyori2Bamei"] = self.decode_field(data[490:526])

            # 23-1. <最近重賞勝利情報> 1件目 年月日場回日R (位置:527, 長さ:16)
            result["SaikinJyusyo1SaikinJyusyoid"] = self.decode_field(data[526:542])

            # 23-1. <最近重賞勝利情報> 1件目 競走名本題 (位置:543, 長さ:60)
            result["SaikinJyusyo1Hondai"] = self.decode_field(data[542:602])

            # 23-1. <最近重賞勝利情報> 1件目 競走名略称10文字 (位置:603, 長さ:20)
            result["SaikinJyusyo1Ryakusyo10"] = self.decode_field(data[602:622])

            # 23-1. <最近重賞勝利情報> 1件目 競走名略称6文字 (位置:623, 長さ:12)
            result["SaikinJyusyo1Ryakusyo6"] = self.decode_field(data[622:634])

            # 23-1. <最近重賞勝利情報> 1件目 競走名略称3文字 (位置:635, 長さ:6)
            result["SaikinJyusyo1Ryakusyo3"] = self.decode_field(data[634:640])

            # 23-1. <最近重賞勝利情報> 1件目 グレードコード (位置:641, 長さ:1)
            result["SaikinJyusyo1GradeCD"] = self.decode_field(data[640:641])

            # 23-1. <最近重賞勝利情報> 1件目 出走頭数 (位置:642, 長さ:2)
            result["SaikinJyusyo1SyussoTosu"] = self.decode_field(data[641:643])

            # 23-1. <最近重賞勝利情報> 1件目 血統登録番号 (位置:644, 長さ:10)
            result["SaikinJyusyo1KettoNum"] = self.decode_field(data[643:653])

            # 23-1. <最近重賞勝利情報> 1件目 馬名 (位置:654, 長さ:36)
            result["SaikinJyusyo1Bamei"] = self.decode_field(data[653:689])

            # 23-2. <最近重賞勝利情報> 2件目 年月日場回日R (位置:690, 長さ:16)
            result["SaikinJyusyo2SaikinJyusyoid"] = self.decode_field(data[689:705])

            # 23-2. <最近重賞勝利情報> 2件目 競走名本題 (位置:706, 長さ:60)
            result["SaikinJyusyo2Hondai"] = self.decode_field(data[705:765])

            # 23-2. <最近重賞勝利情報> 2件目 競走名略称10文字 (位置:766, 長さ:20)
            result["SaikinJyusyo2Ryakusyo10"] = self.decode_field(data[765:785])

            # 23-2. <最近重賞勝利情報> 2件目 競走名略称6文字 (位置:786, 長さ:12)
            result["SaikinJyusyo2Ryakusyo6"] = self.decode_field(data[785:797])

            # 23-2. <最近重賞勝利情報> 2件目 競走名略称3文字 (位置:798, 長さ:6)
            result["SaikinJyusyo2Ryakusyo3"] = self.decode_field(data[797:803])

            # 23-2. <最近重賞勝利情報> 2件目 グレードコード (位置:804, 長さ:1)
            result["SaikinJyusyo2GradeCD"] = self.decode_field(data[803:804])

            # 23-2. <最近重賞勝利情報> 2件目 出走頭数 (位置:805, 長さ:2)
            result["SaikinJyusyo2SyussoTosu"] = self.decode_field(data[804:806])

            # 23-2. <最近重賞勝利情報> 2件目 血統登録番号 (位置:807, 長さ:10)
            result["SaikinJyusyo2KettoNum"] = self.decode_field(data[806:816])

            # 23-2. <最近重賞勝利情報> 2件目 馬名 (位置:817, 長さ:36)
            result["SaikinJyusyo2Bamei"] = self.decode_field(data[816:852])

            # 23-3. <最近重賞勝利情報> 3件目 年月日場回日R (位置:853, 長さ:16)
            result["SaikinJyusyo3SaikinJyusyoid"] = self.decode_field(data[852:868])

            # 23-3. <最近重賞勝利情報> 3件目 競走名本題 (位置:869, 長さ:60)
            result["SaikinJyusyo3Hondai"] = self.decode_field(data[868:928])

            # 23-3. <最近重賞勝利情報> 3件目 競走名略称10文字 (位置:929, 長さ:20)
            result["SaikinJyusyo3Ryakusyo10"] = self.decode_field(data[928:948])

            # 23-3. <最近重賞勝利情報> 3件目 競走名略称6文字 (位置:949, 長さ:12)
            result["SaikinJyusyo3Ryakusyo6"] = self.decode_field(data[948:960])

            # 23-3. <最近重賞勝利情報> 3件目 競走名略称3文字 (位置:961, 長さ:6)
            result["SaikinJyusyo3Ryakusyo3"] = self.decode_field(data[960:966])

            # 23-3. <最近重賞勝利情報> 3件目 グレードコード (位置:967, 長さ:1)
            result["SaikinJyusyo3GradeCD"] = self.decode_field(data[966:967])

            # 23-3. <最近重賞勝利情報> 3件目 出走頭数 (位置:968, 長さ:2)
            result["SaikinJyusyo3SyussoTosu"] = self.decode_field(data[967:969])

            # 23-3. <最近重賞勝利情報> 3件目 血統登録番号 (位置:970, 長さ:10)
            result["SaikinJyusyo3KettoNum"] = self.decode_field(data[969:979])

            # 23-3. <最近重賞勝利情報> 3件目 馬名 (位置:980, 長さ:36)
            result["SaikinJyusyo3Bamei"] = self.decode_field(data[979:1015])

            # 24-1. <本年･前年･累計成績情報> 本年 設定年 (位置:1016, 長さ:4)
            result["Seiseki1SetYear"] = self.decode_field(data[1015:1019])

            # 24-1. <本年･前年･累計成績情報> 本年 平地本賞金合計 (位置:1020, 長さ:10)
            result["Seiseki1HonSyokinH"] = self.decode_field(data[1019:1029])

            # 24-1. <本年･前年･累計成績情報> 本年 障害本賞金合計 (位置:1030, 長さ:10)
            result["Seiseki1HonSyokinS"] = self.decode_field(data[1029:1039])

            # 24-1. <本年･前年･累計成績情報> 本年 平地付加賞金合計 (位置:1040, 長さ:10)
            result["Seiseki1FukaSyokinH"] = self.decode_field(data[1039:1049])

            # 24-1. <本年･前年･累計成績情報> 本年 障害付加賞金合計 (位置:1050, 長さ:10)
            result["Seiseki1FukaSyokinS"] = self.decode_field(data[1049:1059])

            # 24-1. <本年･前年･累計成績情報> 本年 平地着回数 (位置:1060, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuH"] = self.decode_field(data[1059:1095])
            # 24-1. <本年･前年･累計成績情報> 本年 障害着回数 (位置:1096, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuS"] = self.decode_field(data[1095:1131])
            # 24-1. <本年･前年･累計成績情報> 本年 札幌平地着回数 (位置:1132, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu01H"] = self.decode_field(data[1131:1167])
            # 24-1. <本年･前年･累計成績情報> 本年 札幌障害着回数 (位置:1168, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu01S"] = self.decode_field(data[1167:1203])
            # 24-1. <本年･前年･累計成績情報> 本年 函館平地着回数 (位置:1204, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu02H"] = self.decode_field(data[1203:1239])
            # 24-1. <本年･前年･累計成績情報> 本年 函館障害着回数 (位置:1240, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu02S"] = self.decode_field(data[1239:1275])
            # 24-1. <本年･前年･累計成績情報> 本年 福島平地着回数 (位置:1276, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu03H"] = self.decode_field(data[1275:1311])
            # 24-1. <本年･前年･累計成績情報> 本年 福島障害着回数 (位置:1312, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu03S"] = self.decode_field(data[1311:1347])
            # 24-1. <本年･前年･累計成績情報> 本年 新潟平地着回数 (位置:1348, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu04H"] = self.decode_field(data[1347:1383])
            # 24-1. <本年･前年･累計成績情報> 本年 新潟障害着回数 (位置:1384, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu04S"] = self.decode_field(data[1383:1419])
            # 24-1. <本年･前年･累計成績情報> 本年 東京平地着回数 (位置:1420, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu05H"] = self.decode_field(data[1419:1455])
            # 24-1. <本年･前年･累計成績情報> 本年 東京障害着回数 (位置:1456, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu05S"] = self.decode_field(data[1455:1491])
            # 24-1. <本年･前年･累計成績情報> 本年 中山平地着回数 (位置:1492, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu06H"] = self.decode_field(data[1491:1527])
            # 24-1. <本年･前年･累計成績情報> 本年 中山障害着回数 (位置:1528, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu06S"] = self.decode_field(data[1527:1563])
            # 24-1. <本年･前年･累計成績情報> 本年 中京平地着回数 (位置:1564, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu07H"] = self.decode_field(data[1563:1599])
            # 24-1. <本年･前年･累計成績情報> 本年 中京障害着回数 (位置:1600, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu07S"] = self.decode_field(data[1599:1635])
            # 24-1. <本年･前年･累計成績情報> 本年 京都平地着回数 (位置:1636, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu08H"] = self.decode_field(data[1635:1671])
            # 24-1. <本年･前年･累計成績情報> 本年 京都障害着回数 (位置:1672, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu08S"] = self.decode_field(data[1671:1707])
            # 24-1. <本年･前年･累計成績情報> 本年 阪神平地着回数 (位置:1708, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu09H"] = self.decode_field(data[1707:1743])
            # 24-1. <本年･前年･累計成績情報> 本年 阪神障害着回数 (位置:1744, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu09S"] = self.decode_field(data[1743:1779])
            # 24-1. <本年･前年･累計成績情報> 本年 小倉平地着回数 (位置:1780, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu10H"] = self.decode_field(data[1779:1815])
            # 24-1. <本年･前年･累計成績情報> 本年 小倉障害着回数 (位置:1816, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu10S"] = self.decode_field(data[1815:1851])
            # 24-1. <本年･前年･累計成績情報> 本年 芝16下・着回数 (位置:1852, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuSiba1"] = self.decode_field(data[1851:1887])
            # 24-1. <本年･前年･累計成績情報> 本年 芝22下・着回数 (位置:1888, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuSiba2"] = self.decode_field(data[1887:1923])
            # 24-1. <本年･前年･累計成績情報> 本年 芝22超・着回数 (位置:1924, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuSiba3"] = self.decode_field(data[1923:1959])
            # 24-1. <本年･前年･累計成績情報> 本年 ダ16下・着回数 (位置:1960, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuDirt1"] = self.decode_field(data[1959:1995])
            # 24-1. <本年･前年･累計成績情報> 本年 ダ22下・着回数 (位置:1996, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuDirt2"] = self.decode_field(data[1995:2031])
            # 24-1. <本年･前年･累計成績情報> 本年 ダ22超・着回数 (位置:2032, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuDirt3"] = self.decode_field(data[2031:2067])
            # 24-2. <本年･前年･累計成績情報> 前年 設定年 (位置:2068, 長さ:4)
            result["Seiseki2SetYear"] = self.decode_field(data[2067:2071])

            # 24-2. <本年･前年･累計成績情報> 前年 平地本賞金合計 (位置:2072, 長さ:10)
            result["Seiseki2HonSyokinH"] = self.decode_field(data[2071:2081])

            # 24-2. <本年･前年･累計成績情報> 前年 障害本賞金合計 (位置:2082, 長さ:10)
            result["Seiseki2HonSyokinS"] = self.decode_field(data[2081:2091])

            # 24-2. <本年･前年･累計成績情報> 前年 平地付加賞金合計 (位置:2092, 長さ:10)
            result["Seiseki2FukaSyokinH"] = self.decode_field(data[2091:2101])

            # 24-2. <本年･前年･累計成績情報> 前年 障害付加賞金合計 (位置:2102, 長さ:10)
            result["Seiseki2FukaSyokinS"] = self.decode_field(data[2101:2111])

            # 24-2. <本年･前年･累計成績情報> 前年 平地着回数 (位置:2112, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuH"] = self.decode_field(data[2111:2147])
            # 24-2. <本年･前年･累計成績情報> 前年 障害着回数 (位置:2148, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuS"] = self.decode_field(data[2147:2183])
            # 24-2. <本年･前年･累計成績情報> 前年 札幌平地着回数 (位置:2184, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu01H"] = self.decode_field(data[2183:2219])
            # 24-2. <本年･前年･累計成績情報> 前年 札幌障害着回数 (位置:2220, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu01S"] = self.decode_field(data[2219:2255])
            # 24-2. <本年･前年･累計成績情報> 前年 函館平地着回数 (位置:2256, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu02H"] = self.decode_field(data[2255:2291])
            # 24-2. <本年･前年･累計成績情報> 前年 函館障害着回数 (位置:2292, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu02S"] = self.decode_field(data[2291:2327])
            # 24-2. <本年･前年･累計成績情報> 前年 福島平地着回数 (位置:2328, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu03H"] = self.decode_field(data[2327:2363])
            # 24-2. <本年･前年･累計成績情報> 前年 福島障害着回数 (位置:2364, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu03S"] = self.decode_field(data[2363:2399])
            # 24-2. <本年･前年･累計成績情報> 前年 新潟平地着回数 (位置:2400, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu04H"] = self.decode_field(data[2399:2435])
            # 24-2. <本年･前年･累計成績情報> 前年 新潟障害着回数 (位置:2436, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu04S"] = self.decode_field(data[2435:2471])
            # 24-2. <本年･前年･累計成績情報> 前年 東京平地着回数 (位置:2472, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu05H"] = self.decode_field(data[2471:2507])
            # 24-2. <本年･前年･累計成績情報> 前年 東京障害着回数 (位置:2508, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu05S"] = self.decode_field(data[2507:2543])
            # 24-2. <本年･前年･累計成績情報> 前年 中山平地着回数 (位置:2544, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu06H"] = self.decode_field(data[2543:2579])
            # 24-2. <本年･前年･累計成績情報> 前年 中山障害着回数 (位置:2580, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu06S"] = self.decode_field(data[2579:2615])
            # 24-2. <本年･前年･累計成績情報> 前年 中京平地着回数 (位置:2616, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu07H"] = self.decode_field(data[2615:2651])
            # 24-2. <本年･前年･累計成績情報> 前年 中京障害着回数 (位置:2652, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu07S"] = self.decode_field(data[2651:2687])
            # 24-2. <本年･前年･累計成績情報> 前年 京都平地着回数 (位置:2688, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu08H"] = self.decode_field(data[2687:2723])
            # 24-2. <本年･前年･累計成績情報> 前年 京都障害着回数 (位置:2724, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu08S"] = self.decode_field(data[2723:2759])
            # 24-2. <本年･前年･累計成績情報> 前年 阪神平地着回数 (位置:2760, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu09H"] = self.decode_field(data[2759:2795])
            # 24-2. <本年･前年･累計成績情報> 前年 阪神障害着回数 (位置:2796, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu09S"] = self.decode_field(data[2795:2831])
            # 24-2. <本年･前年･累計成績情報> 前年 小倉平地着回数 (位置:2832, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu10H"] = self.decode_field(data[2831:2867])
            # 24-2. <本年･前年･累計成績情報> 前年 小倉障害着回数 (位置:2868, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu10S"] = self.decode_field(data[2867:2903])
            # 24-2. <本年･前年･累計成績情報> 前年 芝16下・着回数 (位置:2904, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuSiba1"] = self.decode_field(data[2903:2939])
            # 24-2. <本年･前年･累計成績情報> 前年 芝22下・着回数 (位置:2940, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuSiba2"] = self.decode_field(data[2939:2975])
            # 24-2. <本年･前年･累計成績情報> 前年 芝22超・着回数 (位置:2976, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuSiba3"] = self.decode_field(data[2975:3011])
            # 24-2. <本年･前年･累計成績情報> 前年 ダ16下・着回数 (位置:3012, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuDirt1"] = self.decode_field(data[3011:3047])
            # 24-2. <本年･前年･累計成績情報> 前年 ダ22下・着回数 (位置:3048, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuDirt2"] = self.decode_field(data[3047:3083])
            # 24-2. <本年･前年･累計成績情報> 前年 ダ22超・着回数 (位置:3084, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuDirt3"] = self.decode_field(data[3083:3119])
            # 24-3. <本年･前年･累計成績情報> 累計 設定年 (位置:3120, 長さ:4)
            result["Seiseki3SetYear"] = self.decode_field(data[3119:3123])

            # 24-3. <本年･前年･累計成績情報> 累計 平地本賞金合計 (位置:3124, 長さ:10)
            result["Seiseki3HonSyokinH"] = self.decode_field(data[3123:3133])

            # 24-3. <本年･前年･累計成績情報> 累計 障害本賞金合計 (位置:3134, 長さ:10)
            result["Seiseki3HonSyokinS"] = self.decode_field(data[3133:3143])

            # 24-3. <本年･前年･累計成績情報> 累計 平地付加賞金合計 (位置:3144, 長さ:10)
            result["Seiseki3FukaSyokinH"] = self.decode_field(data[3143:3153])

            # 24-3. <本年･前年･累計成績情報> 累計 障害付加賞金合計 (位置:3154, 長さ:10)
            result["Seiseki3FukaSyokinS"] = self.decode_field(data[3153:3163])

            # 24-3. <本年･前年･累計成績情報> 累計 平地着回数 (位置:3164, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuH"] = self.decode_field(data[3163:3199])
            # 24-3. <本年･前年･累計成績情報> 累計 障害着回数 (位置:3200, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuS"] = self.decode_field(data[3199:3235])
            # 24-3. <本年･前年･累計成績情報> 累計 札幌平地着回数 (位置:3236, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu01H"] = self.decode_field(data[3235:3271])
            # 24-3. <本年･前年･累計成績情報> 累計 札幌障害着回数 (位置:3272, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu01S"] = self.decode_field(data[3271:3307])
            # 24-3. <本年･前年･累計成績情報> 累計 函館平地着回数 (位置:3308, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu02H"] = self.decode_field(data[3307:3343])
            # 24-3. <本年･前年･累計成績情報> 累計 函館障害着回数 (位置:3344, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu02S"] = self.decode_field(data[3343:3379])
            # 24-3. <本年･前年･累計成績情報> 累計 福島平地着回数 (位置:3380, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu03H"] = self.decode_field(data[3379:3415])
            # 24-3. <本年･前年･累計成績情報> 累計 福島障害着回数 (位置:3416, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu03S"] = self.decode_field(data[3415:3451])
            # 24-3. <本年･前年･累計成績情報> 累計 新潟平地着回数 (位置:3452, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu04H"] = self.decode_field(data[3451:3487])
            # 24-3. <本年･前年･累計成績情報> 累計 新潟障害着回数 (位置:3488, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu04S"] = self.decode_field(data[3487:3523])
            # 24-3. <本年･前年･累計成績情報> 累計 東京平地着回数 (位置:3524, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu05H"] = self.decode_field(data[3523:3559])
            # 24-3. <本年･前年･累計成績情報> 累計 東京障害着回数 (位置:3560, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu05S"] = self.decode_field(data[3559:3595])
            # 24-3. <本年･前年･累計成績情報> 累計 中山平地着回数 (位置:3596, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu06H"] = self.decode_field(data[3595:3631])
            # 24-3. <本年･前年･累計成績情報> 累計 中山障害着回数 (位置:3632, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu06S"] = self.decode_field(data[3631:3667])
            # 24-3. <本年･前年･累計成績情報> 累計 中京平地着回数 (位置:3668, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu07H"] = self.decode_field(data[3667:3703])
            # 24-3. <本年･前年･累計成績情報> 累計 中京障害着回数 (位置:3704, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu07S"] = self.decode_field(data[3703:3739])
            # 24-3. <本年･前年･累計成績情報> 累計 京都平地着回数 (位置:3740, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu08H"] = self.decode_field(data[3739:3775])
            # 24-3. <本年･前年･累計成績情報> 累計 京都障害着回数 (位置:3776, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu08S"] = self.decode_field(data[3775:3811])
            # 24-3. <本年･前年･累計成績情報> 累計 阪神平地着回数 (位置:3812, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu09H"] = self.decode_field(data[3811:3847])
            # 24-3. <本年･前年･累計成績情報> 累計 阪神障害着回数 (位置:3848, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu09S"] = self.decode_field(data[3847:3883])
            # 24-3. <本年･前年･累計成績情報> 累計 小倉平地着回数 (位置:3884, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu10H"] = self.decode_field(data[3883:3919])
            # 24-3. <本年･前年･累計成績情報> 累計 小倉障害着回数 (位置:3920, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu10S"] = self.decode_field(data[3919:3955])
            # 24-3. <本年･前年･累計成績情報> 累計 芝16下・着回数 (位置:3956, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuSiba1"] = self.decode_field(data[3955:3991])
            # 24-3. <本年･前年･累計成績情報> 累計 芝22下・着回数 (位置:3992, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuSiba2"] = self.decode_field(data[3991:4027])
            # 24-3. <本年･前年･累計成績情報> 累計 芝22超・着回数 (位置:4028, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuSiba3"] = self.decode_field(data[4027:4063])
            # 24-3. <本年･前年･累計成績情報> 累計 ダ16下・着回数 (位置:4064, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuDirt1"] = self.decode_field(data[4063:4099])
            # 24-3. <本年･前年･累計成績情報> 累計 ダ22下・着回数 (位置:4100, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuDirt2"] = self.decode_field(data[4099:4135])
            # 24-3. <本年･前年･累計成績情報> 累計 ダ22超・着回数 (位置:4136, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuDirt3"] = self.decode_field(data[4135:4171])
            # 25. レコード区切 (位置:4172, 長さ:2)
            result["crlf"] = self.decode_field(data[4171:4173])

            return result

        except Exception as e:
            self.logger.error(f"KSレコードパース中にエラー: {e}")
            return None

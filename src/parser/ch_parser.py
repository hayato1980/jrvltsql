#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CHレコードパーサー: １５．調教師マスタ

Source: 公式JV-Data仕様書 Ver.4.9.0.1 「１５．調教師マスタ」
"""

from typing import Dict, Optional
from src.utils.logger import get_logger


class CHParser:
    """
    CHレコードパーサー

    １５．調教師マスタ
    レコード長: 3862 bytes
    VBテーブル名: CHOKYO
    """

    RECORD_TYPE = "CH"
    RECORD_LENGTH = 3862

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
        CHレコードをパースしてフィールド辞書を返す

        Args:
            data: パース対象のバイトデータ

        Returns:
            フィールド名をキーとした辞書、エラー時はNone
        """
        try:
            # レコード長チェック
            if len(data) < self.RECORD_LENGTH:
                self.logger.warning(
                    f"CHレコード長不足: expected={self.RECORD_LENGTH}, actual={len(data)}"
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

            # 4. 調教師コード (位置:12, 長さ:5)
            result["ChokyosiCode"] = self.decode_field(data[11:16])

            # 5. 調教師抹消区分 (位置:17, 長さ:1)
            result["DelKubun"] = self.decode_field(data[16:17])

            # 6. 調教師免許交付年月日 (位置:18, 長さ:8)
            result["IssueDate"] = self.decode_field(data[17:25])

            # 7. 調教師免許抹消年月日 (位置:26, 長さ:8)
            result["DelDate"] = self.decode_field(data[25:33])

            # 8. 生年月日 (位置:34, 長さ:8)
            result["BirthDate"] = self.decode_field(data[33:41])

            # 9. 調教師名 (位置:42, 長さ:34)
            result["ChokyosiName"] = self.decode_field(data[41:75])

            # 10. 調教師名半角ｶﾅ (位置:76, 長さ:30)
            result["ChokyosiNameKana"] = self.decode_field(data[75:105])

            # 11. 調教師名略称 (位置:106, 長さ:8)
            result["ChokyosiRyakusyo"] = self.decode_field(data[105:113])

            # 12. 調教師名欧字 (位置:114, 長さ:80)
            result["ChokyosiNameEng"] = self.decode_field(data[113:193])

            # 13. 性別区分 (位置:194, 長さ:1)
            result["SexCD"] = self.decode_field(data[193:194])

            # 14. 調教師東西所属コード (位置:195, 長さ:1)
            result["TozaiCD"] = self.decode_field(data[194:195])

            # 15. 招待地域名 (位置:196, 長さ:20)
            result["Syotai"] = self.decode_field(data[195:215])

            # 16. <最近重賞勝利情報> (位置:216, 長さ:0)
            # 17. 　　年月日場回日R (位置:216, 長さ:16)
            result["SaikinJyusyo1_id"] = self.decode_field(data[215:231])

            # 18. 　　競走名本題 (位置:232, 長さ:60)
            result["SaikinJyusyo1_Hondai"] = self.decode_field(data[231:291])

            # 19. 　　競走名略称10文字 (位置:292, 長さ:20)
            result["SaikinJyusyo1_Ryakusyo10"] = self.decode_field(data[291:311])

            # 20. 　　競走名略称6文字 (位置:312, 長さ:12)
            result["SaikinJyusyo1_Ryakusyo6"] = self.decode_field(data[311:323])

            # 21. 　　競走名略称3文字 (位置:324, 長さ:6)
            result["SaikinJyusyo1_Ryakusyo3"] = self.decode_field(data[323:329])

            # 22. 　　グレードコード (位置:330, 長さ:1)
            result["SaikinJyusyo1_GradeCD"] = self.decode_field(data[329:330])

            # 23. 　　出走頭数 (位置:331, 長さ:2)
            result["SaikinJyusyo1_SyussoTosu"] = self.decode_field(data[330:332])

            # 24. 　　血統登録番号 (位置:333, 長さ:10)
            result["SaikinJyusyo1_KettoNum"] = self.decode_field(data[332:342])

            # 25. 　　馬名 (位置:343, 長さ:36)
            result["SaikinJyusyo1_Bamei"] = self.decode_field(data[342:378])

            # 16-2. <最近重賞勝利情報> 2件目 年月日場回日R (位置:379, 長さ:16)
            result["SaikinJyusyo2_id"] = self.decode_field(data[378:394])

            # 16-2. <最近重賞勝利情報> 2件目 競走名本題 (位置:395, 長さ:60)
            result["SaikinJyusyo2_Hondai"] = self.decode_field(data[394:454])

            # 16-2. <最近重賞勝利情報> 2件目 競走名略称10文字 (位置:455, 長さ:20)
            result["SaikinJyusyo2_Ryakusyo10"] = self.decode_field(data[454:474])

            # 16-2. <最近重賞勝利情報> 2件目 競走名略称6文字 (位置:475, 長さ:12)
            result["SaikinJyusyo2_Ryakusyo6"] = self.decode_field(data[474:486])

            # 16-2. <最近重賞勝利情報> 2件目 競走名略称3文字 (位置:487, 長さ:6)
            result["SaikinJyusyo2_Ryakusyo3"] = self.decode_field(data[486:492])

            # 16-2. <最近重賞勝利情報> 2件目 グレードコード (位置:493, 長さ:1)
            result["SaikinJyusyo2_GradeCD"] = self.decode_field(data[492:493])

            # 16-2. <最近重賞勝利情報> 2件目 出走頭数 (位置:494, 長さ:2)
            result["SaikinJyusyo2_SyussoTosu"] = self.decode_field(data[493:495])

            # 16-2. <最近重賞勝利情報> 2件目 血統登録番号 (位置:496, 長さ:10)
            result["SaikinJyusyo2_KettoNum"] = self.decode_field(data[495:505])

            # 16-2. <最近重賞勝利情報> 2件目 馬名 (位置:506, 長さ:36)
            result["SaikinJyusyo2_Bamei"] = self.decode_field(data[505:541])

            # 16-3. <最近重賞勝利情報> 3件目 年月日場回日R (位置:542, 長さ:16)
            result["SaikinJyusyo3_id"] = self.decode_field(data[541:557])

            # 16-3. <最近重賞勝利情報> 3件目 競走名本題 (位置:558, 長さ:60)
            result["SaikinJyusyo3_Hondai"] = self.decode_field(data[557:617])

            # 16-3. <最近重賞勝利情報> 3件目 競走名略称10文字 (位置:618, 長さ:20)
            result["SaikinJyusyo3_Ryakusyo10"] = self.decode_field(data[617:637])

            # 16-3. <最近重賞勝利情報> 3件目 競走名略称6文字 (位置:638, 長さ:12)
            result["SaikinJyusyo3_Ryakusyo6"] = self.decode_field(data[637:649])

            # 16-3. <最近重賞勝利情報> 3件目 競走名略称3文字 (位置:650, 長さ:6)
            result["SaikinJyusyo3_Ryakusyo3"] = self.decode_field(data[649:655])

            # 16-3. <最近重賞勝利情報> 3件目 グレードコード (位置:656, 長さ:1)
            result["SaikinJyusyo3_GradeCD"] = self.decode_field(data[655:656])

            # 16-3. <最近重賞勝利情報> 3件目 出走頭数 (位置:657, 長さ:2)
            result["SaikinJyusyo3_SyussoTosu"] = self.decode_field(data[656:658])

            # 16-3. <最近重賞勝利情報> 3件目 血統登録番号 (位置:659, 長さ:10)
            result["SaikinJyusyo3_KettoNum"] = self.decode_field(data[658:668])

            # 16-3. <最近重賞勝利情報> 3件目 馬名 (位置:669, 長さ:36)
            result["SaikinJyusyo3_Bamei"] = self.decode_field(data[668:704])

            # 17-1. <本年･前年･累計成績情報> 本年 設定年 (位置:705, 長さ:4)
            result["Seiseki1SetYear"] = self.decode_field(data[704:708])

            # 17-1. <本年･前年･累計成績情報> 本年 平地本賞金合計 (位置:709, 長さ:10)
            result["Seiseki1HonSyokinH"] = self.decode_field(data[708:718])

            # 17-1. <本年･前年･累計成績情報> 本年 障害本賞金合計 (位置:719, 長さ:10)
            result["Seiseki1HonSyokinS"] = self.decode_field(data[718:728])

            # 17-1. <本年･前年･累計成績情報> 本年 平地付加賞金合計 (位置:729, 長さ:10)
            result["Seiseki1FukaSyokinH"] = self.decode_field(data[728:738])

            # 17-1. <本年･前年･累計成績情報> 本年 障害付加賞金合計 (位置:739, 長さ:10)
            result["Seiseki1FukaSyokinS"] = self.decode_field(data[738:748])

            # 17-1. <本年･前年･累計成績情報> 本年 平地着回数 (位置:749, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuH"] = self.decode_field(data[748:784])
            # 17-1. <本年･前年･累計成績情報> 本年 障害着回数 (位置:785, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuS"] = self.decode_field(data[784:820])
            # 17-1. <本年･前年･累計成績情報> 本年 札幌平地着回数 (位置:821, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu01H"] = self.decode_field(data[820:856])
            # 17-1. <本年･前年･累計成績情報> 本年 札幌障害着回数 (位置:857, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu01S"] = self.decode_field(data[856:892])
            # 17-1. <本年･前年･累計成績情報> 本年 函館平地着回数 (位置:893, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu02H"] = self.decode_field(data[892:928])
            # 17-1. <本年･前年･累計成績情報> 本年 函館障害着回数 (位置:929, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu02S"] = self.decode_field(data[928:964])
            # 17-1. <本年･前年･累計成績情報> 本年 福島平地着回数 (位置:965, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu03H"] = self.decode_field(data[964:1000])
            # 17-1. <本年･前年･累計成績情報> 本年 福島障害着回数 (位置:1001, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu03S"] = self.decode_field(data[1000:1036])
            # 17-1. <本年･前年･累計成績情報> 本年 新潟平地着回数 (位置:1037, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu04H"] = self.decode_field(data[1036:1072])
            # 17-1. <本年･前年･累計成績情報> 本年 新潟障害着回数 (位置:1073, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu04S"] = self.decode_field(data[1072:1108])
            # 17-1. <本年･前年･累計成績情報> 本年 東京平地着回数 (位置:1109, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu05H"] = self.decode_field(data[1108:1144])
            # 17-1. <本年･前年･累計成績情報> 本年 東京障害着回数 (位置:1145, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu05S"] = self.decode_field(data[1144:1180])
            # 17-1. <本年･前年･累計成績情報> 本年 中山平地着回数 (位置:1181, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu06H"] = self.decode_field(data[1180:1216])
            # 17-1. <本年･前年･累計成績情報> 本年 中山障害着回数 (位置:1217, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu06S"] = self.decode_field(data[1216:1252])
            # 17-1. <本年･前年･累計成績情報> 本年 中京平地着回数 (位置:1253, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu07H"] = self.decode_field(data[1252:1288])
            # 17-1. <本年･前年･累計成績情報> 本年 中京障害着回数 (位置:1289, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu07S"] = self.decode_field(data[1288:1324])
            # 17-1. <本年･前年･累計成績情報> 本年 京都平地着回数 (位置:1325, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu08H"] = self.decode_field(data[1324:1360])
            # 17-1. <本年･前年･累計成績情報> 本年 京都障害着回数 (位置:1361, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu08S"] = self.decode_field(data[1360:1396])
            # 17-1. <本年･前年･累計成績情報> 本年 阪神平地着回数 (位置:1397, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu09H"] = self.decode_field(data[1396:1432])
            # 17-1. <本年･前年･累計成績情報> 本年 阪神障害着回数 (位置:1433, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu09S"] = self.decode_field(data[1432:1468])
            # 17-1. <本年･前年･累計成績情報> 本年 小倉平地着回数 (位置:1469, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu10H"] = self.decode_field(data[1468:1504])
            # 17-1. <本年･前年･累計成績情報> 本年 小倉障害着回数 (位置:1505, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisu10S"] = self.decode_field(data[1504:1540])
            # 17-1. <本年･前年･累計成績情報> 本年 芝16下・着回数 (位置:1541, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuSiba1"] = self.decode_field(data[1540:1576])
            # 17-1. <本年･前年･累計成績情報> 本年 芝22下・着回数 (位置:1577, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuSiba2"] = self.decode_field(data[1576:1612])
            # 17-1. <本年･前年･累計成績情報> 本年 芝22超・着回数 (位置:1613, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuSiba3"] = self.decode_field(data[1612:1648])
            # 17-1. <本年･前年･累計成績情報> 本年 ダ16下・着回数 (位置:1649, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuDirt1"] = self.decode_field(data[1648:1684])
            # 17-1. <本年･前年･累計成績情報> 本年 ダ22下・着回数 (位置:1685, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuDirt2"] = self.decode_field(data[1684:1720])
            # 17-1. <本年･前年･累計成績情報> 本年 ダ22超・着回数 (位置:1721, 繰返:6, 長さ:6 = 36)
            result["Seiseki1ChakuKaisuDirt3"] = self.decode_field(data[1720:1756])
            # 17-2. <本年･前年･累計成績情報> 前年 設定年 (位置:1757, 長さ:4)
            result["Seiseki2SetYear"] = self.decode_field(data[1756:1760])

            # 17-2. <本年･前年･累計成績情報> 前年 平地本賞金合計 (位置:1761, 長さ:10)
            result["Seiseki2HonSyokinH"] = self.decode_field(data[1760:1770])

            # 17-2. <本年･前年･累計成績情報> 前年 障害本賞金合計 (位置:1771, 長さ:10)
            result["Seiseki2HonSyokinS"] = self.decode_field(data[1770:1780])

            # 17-2. <本年･前年･累計成績情報> 前年 平地付加賞金合計 (位置:1781, 長さ:10)
            result["Seiseki2FukaSyokinH"] = self.decode_field(data[1780:1790])

            # 17-2. <本年･前年･累計成績情報> 前年 障害付加賞金合計 (位置:1791, 長さ:10)
            result["Seiseki2FukaSyokinS"] = self.decode_field(data[1790:1800])

            # 17-2. <本年･前年･累計成績情報> 前年 平地着回数 (位置:1801, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuH"] = self.decode_field(data[1800:1836])
            # 17-2. <本年･前年･累計成績情報> 前年 障害着回数 (位置:1837, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuS"] = self.decode_field(data[1836:1872])
            # 17-2. <本年･前年･累計成績情報> 前年 札幌平地着回数 (位置:1873, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu01H"] = self.decode_field(data[1872:1908])
            # 17-2. <本年･前年･累計成績情報> 前年 札幌障害着回数 (位置:1909, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu01S"] = self.decode_field(data[1908:1944])
            # 17-2. <本年･前年･累計成績情報> 前年 函館平地着回数 (位置:1945, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu02H"] = self.decode_field(data[1944:1980])
            # 17-2. <本年･前年･累計成績情報> 前年 函館障害着回数 (位置:1981, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu02S"] = self.decode_field(data[1980:2016])
            # 17-2. <本年･前年･累計成績情報> 前年 福島平地着回数 (位置:2017, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu03H"] = self.decode_field(data[2016:2052])
            # 17-2. <本年･前年･累計成績情報> 前年 福島障害着回数 (位置:2053, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu03S"] = self.decode_field(data[2052:2088])
            # 17-2. <本年･前年･累計成績情報> 前年 新潟平地着回数 (位置:2089, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu04H"] = self.decode_field(data[2088:2124])
            # 17-2. <本年･前年･累計成績情報> 前年 新潟障害着回数 (位置:2125, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu04S"] = self.decode_field(data[2124:2160])
            # 17-2. <本年･前年･累計成績情報> 前年 東京平地着回数 (位置:2161, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu05H"] = self.decode_field(data[2160:2196])
            # 17-2. <本年･前年･累計成績情報> 前年 東京障害着回数 (位置:2197, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu05S"] = self.decode_field(data[2196:2232])
            # 17-2. <本年･前年･累計成績情報> 前年 中山平地着回数 (位置:2233, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu06H"] = self.decode_field(data[2232:2268])
            # 17-2. <本年･前年･累計成績情報> 前年 中山障害着回数 (位置:2269, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu06S"] = self.decode_field(data[2268:2304])
            # 17-2. <本年･前年･累計成績情報> 前年 中京平地着回数 (位置:2305, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu07H"] = self.decode_field(data[2304:2340])
            # 17-2. <本年･前年･累計成績情報> 前年 中京障害着回数 (位置:2341, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu07S"] = self.decode_field(data[2340:2376])
            # 17-2. <本年･前年･累計成績情報> 前年 京都平地着回数 (位置:2377, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu08H"] = self.decode_field(data[2376:2412])
            # 17-2. <本年･前年･累計成績情報> 前年 京都障害着回数 (位置:2413, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu08S"] = self.decode_field(data[2412:2448])
            # 17-2. <本年･前年･累計成績情報> 前年 阪神平地着回数 (位置:2449, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu09H"] = self.decode_field(data[2448:2484])
            # 17-2. <本年･前年･累計成績情報> 前年 阪神障害着回数 (位置:2485, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu09S"] = self.decode_field(data[2484:2520])
            # 17-2. <本年･前年･累計成績情報> 前年 小倉平地着回数 (位置:2521, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu10H"] = self.decode_field(data[2520:2556])
            # 17-2. <本年･前年･累計成績情報> 前年 小倉障害着回数 (位置:2557, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisu10S"] = self.decode_field(data[2556:2592])
            # 17-2. <本年･前年･累計成績情報> 前年 芝16下・着回数 (位置:2593, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuSiba1"] = self.decode_field(data[2592:2628])
            # 17-2. <本年･前年･累計成績情報> 前年 芝22下・着回数 (位置:2629, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuSiba2"] = self.decode_field(data[2628:2664])
            # 17-2. <本年･前年･累計成績情報> 前年 芝22超・着回数 (位置:2665, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuSiba3"] = self.decode_field(data[2664:2700])
            # 17-2. <本年･前年･累計成績情報> 前年 ダ16下・着回数 (位置:2701, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuDirt1"] = self.decode_field(data[2700:2736])
            # 17-2. <本年･前年･累計成績情報> 前年 ダ22下・着回数 (位置:2737, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuDirt2"] = self.decode_field(data[2736:2772])
            # 17-2. <本年･前年･累計成績情報> 前年 ダ22超・着回数 (位置:2773, 繰返:6, 長さ:6 = 36)
            result["Seiseki2ChakuKaisuDirt3"] = self.decode_field(data[2772:2808])
            # 17-3. <本年･前年･累計成績情報> 累計 設定年 (位置:2809, 長さ:4)
            result["Seiseki3SetYear"] = self.decode_field(data[2808:2812])

            # 17-3. <本年･前年･累計成績情報> 累計 平地本賞金合計 (位置:2813, 長さ:10)
            result["Seiseki3HonSyokinH"] = self.decode_field(data[2812:2822])

            # 17-3. <本年･前年･累計成績情報> 累計 障害本賞金合計 (位置:2823, 長さ:10)
            result["Seiseki3HonSyokinS"] = self.decode_field(data[2822:2832])

            # 17-3. <本年･前年･累計成績情報> 累計 平地付加賞金合計 (位置:2833, 長さ:10)
            result["Seiseki3FukaSyokinH"] = self.decode_field(data[2832:2842])

            # 17-3. <本年･前年･累計成績情報> 累計 障害付加賞金合計 (位置:2843, 長さ:10)
            result["Seiseki3FukaSyokinS"] = self.decode_field(data[2842:2852])

            # 17-3. <本年･前年･累計成績情報> 累計 平地着回数 (位置:2853, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuH"] = self.decode_field(data[2852:2888])
            # 17-3. <本年･前年･累計成績情報> 累計 障害着回数 (位置:2889, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuS"] = self.decode_field(data[2888:2924])
            # 17-3. <本年･前年･累計成績情報> 累計 札幌平地着回数 (位置:2925, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu01H"] = self.decode_field(data[2924:2960])
            # 17-3. <本年･前年･累計成績情報> 累計 札幌障害着回数 (位置:2961, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu01S"] = self.decode_field(data[2960:2996])
            # 17-3. <本年･前年･累計成績情報> 累計 函館平地着回数 (位置:2997, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu02H"] = self.decode_field(data[2996:3032])
            # 17-3. <本年･前年･累計成績情報> 累計 函館障害着回数 (位置:3033, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu02S"] = self.decode_field(data[3032:3068])
            # 17-3. <本年･前年･累計成績情報> 累計 福島平地着回数 (位置:3069, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu03H"] = self.decode_field(data[3068:3104])
            # 17-3. <本年･前年･累計成績情報> 累計 福島障害着回数 (位置:3105, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu03S"] = self.decode_field(data[3104:3140])
            # 17-3. <本年･前年･累計成績情報> 累計 新潟平地着回数 (位置:3141, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu04H"] = self.decode_field(data[3140:3176])
            # 17-3. <本年･前年･累計成績情報> 累計 新潟障害着回数 (位置:3177, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu04S"] = self.decode_field(data[3176:3212])
            # 17-3. <本年･前年･累計成績情報> 累計 東京平地着回数 (位置:3213, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu05H"] = self.decode_field(data[3212:3248])
            # 17-3. <本年･前年･累計成績情報> 累計 東京障害着回数 (位置:3249, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu05S"] = self.decode_field(data[3248:3284])
            # 17-3. <本年･前年･累計成績情報> 累計 中山平地着回数 (位置:3285, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu06H"] = self.decode_field(data[3284:3320])
            # 17-3. <本年･前年･累計成績情報> 累計 中山障害着回数 (位置:3321, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu06S"] = self.decode_field(data[3320:3356])
            # 17-3. <本年･前年･累計成績情報> 累計 中京平地着回数 (位置:3357, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu07H"] = self.decode_field(data[3356:3392])
            # 17-3. <本年･前年･累計成績情報> 累計 中京障害着回数 (位置:3393, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu07S"] = self.decode_field(data[3392:3428])
            # 17-3. <本年･前年･累計成績情報> 累計 京都平地着回数 (位置:3429, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu08H"] = self.decode_field(data[3428:3464])
            # 17-3. <本年･前年･累計成績情報> 累計 京都障害着回数 (位置:3465, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu08S"] = self.decode_field(data[3464:3500])
            # 17-3. <本年･前年･累計成績情報> 累計 阪神平地着回数 (位置:3501, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu09H"] = self.decode_field(data[3500:3536])
            # 17-3. <本年･前年･累計成績情報> 累計 阪神障害着回数 (位置:3537, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu09S"] = self.decode_field(data[3536:3572])
            # 17-3. <本年･前年･累計成績情報> 累計 小倉平地着回数 (位置:3573, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu10H"] = self.decode_field(data[3572:3608])
            # 17-3. <本年･前年･累計成績情報> 累計 小倉障害着回数 (位置:3609, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisu10S"] = self.decode_field(data[3608:3644])
            # 17-3. <本年･前年･累計成績情報> 累計 芝16下・着回数 (位置:3645, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuSiba1"] = self.decode_field(data[3644:3680])
            # 17-3. <本年･前年･累計成績情報> 累計 芝22下・着回数 (位置:3681, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuSiba2"] = self.decode_field(data[3680:3716])
            # 17-3. <本年･前年･累計成績情報> 累計 芝22超・着回数 (位置:3717, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuSiba3"] = self.decode_field(data[3716:3752])
            # 17-3. <本年･前年･累計成績情報> 累計 ダ16下・着回数 (位置:3753, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuDirt1"] = self.decode_field(data[3752:3788])
            # 17-3. <本年･前年･累計成績情報> 累計 ダ22下・着回数 (位置:3789, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuDirt2"] = self.decode_field(data[3788:3824])
            # 17-3. <本年･前年･累計成績情報> 累計 ダ22超・着回数 (位置:3825, 繰返:6, 長さ:6 = 36)
            result["Seiseki3ChakuKaisuDirt3"] = self.decode_field(data[3824:3860])
            # 18. レコード区切 (位置:3861, 長さ:2)
            result["RecordDelimiter"] = self.decode_field(data[3860:3862])

            return result

        except Exception as e:
            self.logger.error(f"CHレコードパース中にエラー: {e}")
            return None

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RCレコードパーサー: ２１．レコードマスタ

Source: 公式JV-Data仕様書 Ver.4.9.0.1 「２１．レコードマスタ」
"""

from typing import Dict, Optional
from src.utils.logger import get_logger


class RCParser:
    """
    RCレコードパーサー

    ２１．レコードマスタ
    レコード長: 501 bytes
    VBテーブル名: RECORD
    """

    RECORD_TYPE = "RC"
    RECORD_LENGTH = 501

    def __init__(self):
        self.logger = get_logger(__name__)

    @staticmethod
    def decode_field(data: bytes) -> str:
        """バイトデータをデコードして文字列に変換"""
        try:
            # CP932でデコード、空白を除去
            return data.decode("cp932", errors="replace").strip()
        except Exception:
            return ""

    def parse(self, data: bytes) -> Optional[Dict[str, str]]:
        """
        RCレコードをパースしてフィールド辞書を返す

        Args:
            data: パース対象のバイトデータ

        Returns:
            フィールド名をキーとした辞書、エラー時はNone
        """
        try:
            # レコード長チェック
            if len(data) < self.RECORD_LENGTH:
                self.logger.warning(
                    f"RCレコード長不足: expected={self.RECORD_LENGTH}, actual={len(data)}"
                )
                # return None  # 短いレコードも許容する場合はコメントアウト

            # フィールド抽出
            result = {}

            # 1. レコード種別ID (位置:1-2, 長さ:2)
            result["RecordSpec"] = self.decode_field(data[0:2])

            # 2. データ区分 (位置:3, 長さ:1)
            result["DataKubun"] = self.decode_field(data[2:3])

            # 3. データ作成年月日 (位置:4-11, 長さ:8)
            result["MakeDate"] = self.decode_field(data[3:11])

            # 4. レコード識別区分 (位置:12, 長さ:1)
            result["RecInfoKubun"] = self.decode_field(data[11:12])

            # 5. 開催年 (位置:13-16, 長さ:4)
            result["Year"] = self.decode_field(data[12:16])

            # 6. 開催月日 (位置:17-20, 長さ:4)
            result["MonthDay"] = self.decode_field(data[16:20])

            # 7. 競馬場コード (位置:21-22, 長さ:2)
            result["JyoCD"] = self.decode_field(data[20:22])

            # 8. 開催回[第N回] (位置:23-24, 長さ:2)
            result["Kaiji"] = self.decode_field(data[22:24])

            # 9. 開催日目[N日目] (位置:25-26, 長さ:2)
            result["Nichiji"] = self.decode_field(data[24:26])

            # 10. レース番号 (位置:27-28, 長さ:2)
            result["RaceNum"] = self.decode_field(data[26:28])

            # 11. 特別競走番号 (位置:29-32, 長さ:4)
            result["TokuNum"] = self.decode_field(data[28:32])

            # 12. 競走名本題 (位置:33-92, 長さ:60)
            result["Hondai"] = self.decode_field(data[32:92])

            # 13. グレードコード (位置:93, 長さ:1)
            result["GradeCD"] = self.decode_field(data[92:93])

            # 14. 競走種別コード (位置:94, 長さ:2)
            result["SyubetuCD"] = self.decode_field(data[93:95])

            # 15. 距離 (位置:96-99, 長さ:4)
            result["Kyori"] = self.decode_field(data[95:99])

            # 16. トラックコード (位置:100, 長さ:2)
            result["TrackCD"] = self.decode_field(data[99:101])

            # 17. レコード区分 (位置:102, 長さ:1)
            result["RecKubun"] = self.decode_field(data[101:102])

            # 18. レコードタイム (位置:103, 長さ:4)
            result["RecTime"] = self.decode_field(data[102:106])

            # 19. 天候コード (位置:107, 長さ:1)
            result["TenkoCD"] = self.decode_field(data[106:107])

            # 20. 芝馬場状態コード (位置:108, 長さ:1)
            result["SibaBabaCD"] = self.decode_field(data[107:108])

            # 21. ダート馬場状態コード (位置:109, 長さ:1)
            result["DirtBabaCD"] = self.decode_field(data[108:109])

            # 22-1. <レコード保持馬情報> 1頭目 血統登録番号 (位置:110, 長さ:10)
            result["RecUmaKettoNum1"] = self.decode_field(data[109:119])

            # 22-1. <レコード保持馬情報> 1頭目 馬名 (位置:120, 長さ:36)
            result["RecUmaBamei1"] = self.decode_field(data[119:155])

            # 22-1. <レコード保持馬情報> 1頭目 馬記号コード (位置:156, 長さ:2)
            result["RecUmaUmaKigoCD1"] = self.decode_field(data[155:157])

            # 22-1. <レコード保持馬情報> 1頭目 性別コード (位置:158, 長さ:1)
            result["RecUmaSexCD1"] = self.decode_field(data[157:158])

            # 22-1. <レコード保持馬情報> 1頭目 調教師コード (位置:159, 長さ:5)
            result["RecUmaChokyosiCode1"] = self.decode_field(data[158:163])

            # 22-1. <レコード保持馬情報> 1頭目 調教師名 (位置:164, 長さ:34)
            result["RecUmaChokyosiName1"] = self.decode_field(data[163:197])

            # 22-1. <レコード保持馬情報> 1頭目 負担重量 (位置:198, 長さ:3)
            result["RecUmaFutan1"] = self.decode_field(data[197:200])

            # 22-1. <レコード保持馬情報> 1頭目 騎手コード (位置:201, 長さ:5)
            result["RecUmaKisyuCode1"] = self.decode_field(data[200:205])

            # 22-1. <レコード保持馬情報> 1頭目 騎手名 (位置:206, 長さ:34)
            result["RecUmaKisyuName1"] = self.decode_field(data[205:239])

            # 22-2. <レコード保持馬情報> 2頭目 血統登録番号 (位置:240, 長さ:10)
            result["RecUmaKettoNum2"] = self.decode_field(data[239:249])

            # 22-2. <レコード保持馬情報> 2頭目 馬名 (位置:250, 長さ:36)
            result["RecUmaBamei2"] = self.decode_field(data[249:285])

            # 22-2. <レコード保持馬情報> 2頭目 馬記号コード (位置:286, 長さ:2)
            result["RecUmaUmaKigoCD2"] = self.decode_field(data[285:287])

            # 22-2. <レコード保持馬情報> 2頭目 性別コード (位置:288, 長さ:1)
            result["RecUmaSexCD2"] = self.decode_field(data[287:288])

            # 22-2. <レコード保持馬情報> 2頭目 調教師コード (位置:289, 長さ:5)
            result["RecUmaChokyosiCode2"] = self.decode_field(data[288:293])

            # 22-2. <レコード保持馬情報> 2頭目 調教師名 (位置:294, 長さ:34)
            result["RecUmaChokyosiName2"] = self.decode_field(data[293:327])

            # 22-2. <レコード保持馬情報> 2頭目 負担重量 (位置:328, 長さ:3)
            result["RecUmaFutan2"] = self.decode_field(data[327:330])

            # 22-2. <レコード保持馬情報> 2頭目 騎手コード (位置:331, 長さ:5)
            result["RecUmaKisyuCode2"] = self.decode_field(data[330:335])

            # 22-2. <レコード保持馬情報> 2頭目 騎手名 (位置:336, 長さ:34)
            result["RecUmaKisyuName2"] = self.decode_field(data[335:369])

            # 22-3. <レコード保持馬情報> 3頭目 血統登録番号 (位置:370, 長さ:10)
            result["RecUmaKettoNum3"] = self.decode_field(data[369:379])

            # 22-3. <レコード保持馬情報> 3頭目 馬名 (位置:380, 長さ:36)
            result["RecUmaBamei3"] = self.decode_field(data[379:415])

            # 22-3. <レコード保持馬情報> 3頭目 馬記号コード (位置:416, 長さ:2)
            result["RecUmaUmaKigoCD3"] = self.decode_field(data[415:417])

            # 22-3. <レコード保持馬情報> 3頭目 性別コード (位置:418, 長さ:1)
            result["RecUmaSexCD3"] = self.decode_field(data[417:418])

            # 22-3. <レコード保持馬情報> 3頭目 調教師コード (位置:419, 長さ:5)
            result["RecUmaChokyosiCode3"] = self.decode_field(data[418:423])

            # 22-3. <レコード保持馬情報> 3頭目 調教師名 (位置:424, 長さ:34)
            result["RecUmaChokyosiName3"] = self.decode_field(data[423:457])

            # 22-3. <レコード保持馬情報> 3頭目 負担重量 (位置:458, 長さ:3)
            result["RecUmaFutan3"] = self.decode_field(data[457:460])

            # 22-3. <レコード保持馬情報> 3頭目 騎手コード (位置:461, 長さ:5)
            result["RecUmaKisyuCode3"] = self.decode_field(data[460:465])

            # 22-3. <レコード保持馬情報> 3頭目 騎手名 (位置:466, 長さ:34)
            result["RecUmaKisyuName3"] = self.decode_field(data[465:499])

            # 23. レコード区切 (位置:500, 長さ:2)
            result["RecordDelimiter"] = self.decode_field(data[499:501])

            return result

        except Exception as e:
            self.logger.error(f"RCレコードパース中にエラー: {e}")
            return None

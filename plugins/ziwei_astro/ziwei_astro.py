# encoding:utf-8

import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel.chat_message import ChatMessage
from common.log import logger
from plugins import *
from config import conf
from datetime import datetime
import re

@plugins.register(
    name="ZiweiAstro",
    desire_priority=0,
    hidden=False,
    desc="紫薇斗数排盘插件，支持根据生辰八字信息给出紫微命盘",
    version="0.1",
    author="undermoon_ai_bot",
)
class ZiweiAstro(Plugin):
    def __init__(self):
        super().__init__()
        try:
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            
            # 初始化用户状态字典，用于跟踪用户确认过程
            self.user_states = {}
            
            # 检查py_iztro库是否已安装
            try:
                import py_iztro
                self.py_iztro_available = True
                logger.info("[ZiweiAstro] py_iztro库已成功导入")
            except ImportError:
                self.py_iztro_available = False
                logger.warning("[ZiweiAstro] py_iztro库未安装，将使用模拟数据。建议安装: pip install py-iztro")
            
            # 导入异步处理所需的库
            try:
                import asyncio
                self.asyncio_available = True
            except ImportError:
                self.asyncio_available = False
                logger.warning("[ZiweiAstro] asyncio库导入失败，异步功能可能无法正常工作")
            
            logger.info("[ZiweiAstro] 紫薇斗数排盘插件已初始化")
        except Exception as e:
            logger.error(f"[ZiweiAstro] 初始化异常：{e}")
            raise Exception(f"[ZiweiAstro] 初始化失败: {e}")

    def format_star_list(self, star_list):
        """格式化星曜列表"""
        if not star_list:
            return "无"
        
        formatted_stars = []
        
        # 检查star_list中的元素是字典还是py_iztro的对象
        first_element = star_list[0] if star_list else None
        
        if first_element and hasattr(first_element, 'name'):
            # 处理py_iztro对象
            for star in star_list:
                star_text = star.name
                
                if hasattr(star, 'brightness') and star.brightness:
                    star_text += f"({star.brightness})"
                    
                if hasattr(star, 'mutagen') and star.mutagen:
                    star_text += f"[{star.mutagen}]"
                    
                formatted_stars.append(star_text)
        else:
            # 处理字典格式
        for star in star_list:
            star_text = star.get("name", "")
            
            brightness = star.get("brightness", "")
            if brightness:
                star_text += f"({brightness})"
                
            mutagen = star.get("mutagen", "")
            if mutagen:
                star_text += f"[{mutagen}]"
                
            formatted_stars.append(star_text)
            
        return "、".join(formatted_stars)

    def palace_to_str(self, palace):
        """格式化宫位信息"""
        lines = [
            f"[{palace.get('name', '')}宫] {palace.get('heavenlyStem', '')}{palace.get('earthlyBranch', '')}",
            f"主星: {self.format_star_list(palace.get('majorStars', []))}",
            f"辅星: {self.format_star_list(palace.get('minorStars', []))}",
            f"杂曜: {self.format_star_list(palace.get('adjectiveStars', []))}"
        ]
        
        # 处理四化信息
        main_mutagen = []
        for star in palace.get('majorStars', []):
            if star.get('mutagen'):
                main_mutagen.append(f"{star.get('name', '')}化{star.get('mutagen', '')}")
        
        lines.append(f"四化: {'、'.join(main_mutagen) if main_mutagen else '无'}")
        return '\n'.join(lines)

    def horoscope_to_str(self, horoscope, label):
        """格式化运限信息"""
        if not horoscope:
            return f"【{label}】\n暂无数据"
            
        palace_names = horoscope.get('palaceNames', [])
        
        lines = [
            f"【{label}】",
            f"宫位序列: {'、'.join(palace_names)}",
            f"天干地支: {horoscope.get('heavenlyStem', '')}{horoscope.get('earthlyBranch', '')}",
            f"四化: {'、'.join(horoscope.get('mutagen', [])) if horoscope.get('mutagen') else '无'}",
            "主要星曜分布："
        ]
        
        for idx, stars in enumerate(horoscope.get('stars', [])):
            if stars and idx < len(palace_names):
                lines.append(f"  {palace_names[idx]}宫: {self.format_star_list(stars)}")
                
        return '\n'.join(lines)

    def get_hour_index(self, hour_str):
        """将时辰字符串转换为数字索引
        子=0，丑=1，寅=2，卯=3，辰=4，巳=5，午=6，未=7，申=8，酉=9，戌=10，亥=11
        """
        hour_map = {
            "子": 0, "丑": 1, "寅": 2, "卯": 3, 
            "辰": 4, "巳": 5, "午": 6, "未": 7, 
            "申": 8, "酉": 9, "戌": 10, "亥": 11,
            "0": 0, "1": 1, "2": 2, "3": 3, 
            "4": 4, "5": 5, "6": 6, "7": 7, 
            "8": 8, "9": 9, "10": 10, "11": 11
        }
        return hour_map.get(hour_str, 0)
    
    def simulate_astro_result(self, gender, date_type, date_str, hour_index):
        """
        使用py_iztro库生成紫微斗数排盘结果，如果库不可用则返回模拟数据
        """
        # 检查是否有py_iztro库可用
        if hasattr(self, 'py_iztro_available') and self.py_iztro_available:
            try:
                from py_iztro import Astro
                from datetime import datetime
                
                logger.info(f"[ZiweiAstro] 开始计算紫微斗数: {gender}, {date_type}, {date_str}, {hour_index}")
                
                astro = Astro()
                
                # 调用py_iztro库的方法进行排盘
                if date_type == "公历":
                    result = astro.by_solar(date_str, hour_index, gender)
                elif date_type == "农历":
                    result = astro.by_lunar(date_str, hour_index, gender)
                else:
                    raise ValueError("date_type 只能为 '公历' 或 '农历'")
                
                # 获取今天日期用于运限计算
                today = datetime.today().strftime("%Y-%m-%d")
                horoscope = result.horoscope(today)
                
                logger.info(f"[ZiweiAstro] 紫微斗数计算完成: {result.solar_date}")
                
                return result, horoscope
            except Exception as e:
                logger.error(f"[ZiweiAstro] 使用py_iztro计算紫微斗数出错: {e}")
                logger.info(f"[ZiweiAstro] 将使用模拟数据作为备份")
        else:
            logger.info(f"[ZiweiAstro] py_iztro库不可用，使用模拟数据")
        
        # 生成模拟数据
        hour_names = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
        hour_name = hour_names[hour_index]
        
        # 获取当前日期用于模拟数据
        from datetime import datetime
        today = datetime.today().strftime("%Y-%m-%d")
        
        result = {
            "gender": gender,
            "solarDate": date_str if date_type == "公历" else f"{date_str} (农历转公历)",
            "lunarDate": date_str if date_type == "农历" else f"{date_str} (公历转农历)",
            "chineseDate": f"模拟四柱 {date_str} {hour_name}时",
            "time": f"{hour_name}时",
            "timeRange": f"{hour_index*2}-{(hour_index+1)*2}时",
            "sign": "模拟星座",
            "zodiac": "模拟生肖",
            "earthlyBranchOfSoulPalace": "午",
            "earthlyBranchOfBodyPalace": "戌",
            "soul": "破军",
            "body": "文昌",
            "fiveElementsClass": "木三局",
            "palaces": []
        }
        
        # 添加12宫模拟数据
        palace_names = ["命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄", "迁移", "仆役", "官禄", "田宅", "福德", "父母"]
        heavenly_stems = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
        earthly_branches = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
        
        major_stars = [
            "紫微", "天机", "太阳", "武曲", "天同", "廉贞", "天府", "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "破军"
        ]
        
        minor_stars = [
            "文昌", "文曲", "禄存", "天魁", "天钺", "左辅", "右弼", "天刑", "天姚", "天巫", "天月", "天福"
        ]
        
        adjective_stars = [
            "地空", "地劫", "火星", "铃星", "擎羊", "陀罗", "天空", "天哭", "天虚", "龙池", "凤阁"
        ]
        
        brightness = ["庙", "旺", "得", "平", "闲", "陷"]
        mutagen = ["禄", "权", "科", "忌"]
        
        # 生成12宫位的模拟数据
        for i in range(12):
            # 创建宫位主要信息
            palace = {
                "index": i,
                "name": palace_names[i],
                "isBodyPalace": (i == 8),  # 假设官禄宫是身宫
                "isOriginalPalace": (i == 0),  # 假设命宫是本命宫
                "heavenlyStem": heavenly_stems[i % 10],
                "earthlyBranch": earthly_branches[i % 12],
                "majorStars": [],
                "minorStars": [],
                "adjectiveStars": []
            }
            
            # 为每个宫位随机生成2-3个主星
            import random
            major_count = random.randint(1, 3)
            for j in range(major_count):
                star_index = (i + j) % len(major_stars)
                palace["majorStars"].append({
                    "name": major_stars[star_index],
                        "type": "major",
                        "scope": "origin",
                    "brightness": random.choice(brightness),
                    "mutagen": random.choice(mutagen) if random.random() > 0.7 else ""
                })
            
            # 为每个宫位随机生成1-4个辅星
            minor_count = random.randint(1, 4)
            for j in range(minor_count):
                star_index = (i + j) % len(minor_stars)
                palace["minorStars"].append({
                    "name": minor_stars[star_index],
                        "type": "soft",
                        "scope": "origin",
                    "brightness": random.choice(brightness) if random.random() > 0.6 else "",
                        "mutagen": ""
                })
            
            # 为每个宫位随机生成0-3个杂耀
            adjective_count = random.randint(0, 3)
            for j in range(adjective_count):
                star_index = (i + j) % len(adjective_stars)
                palace["adjectiveStars"].append({
                    "name": adjective_stars[star_index],
                        "type": "adjective",
                        "scope": "origin",
                        "brightness": None,
                        "mutagen": None
                })
            
            result["palaces"].append(palace)
            
        # 模拟运限数据
        horoscope = {
            "decadal": {
                "index": 2,
                "name": "大限",
                "heavenlyStem": "庚",
                "earthlyBranch": "辰",
                "palaceNames": palace_names,
                "mutagen": ["太阳化禄", "武曲化权", "太阴化科", "天同化忌"],
                "stars": [[{"name": f"大限星{i+1}", "type": "decadal", "scope": "decadal", "brightness": None, "mutagen": None}] for i in range(12)]
            },
            "yearly": {
                "index": 6,
                "name": "流年",
                "heavenlyStem": "甲",
                "earthlyBranch": "辰",
                "palaceNames": palace_names,
                "mutagen": ["廉贞化禄", "破军化权", "武曲化科", "太阳化忌"],
                "stars": [[{"name": f"流年星{i+1}", "type": "yearly", "scope": "yearly", "brightness": None, "mutagen": None}] for i in range(12)]
            },
            "monthly": {
                "index": 8,
                "name": "流月",
                "heavenlyStem": "丙",
                "earthlyBranch": "子",
                "palaceNames": palace_names,
                "mutagen": ["天同化禄", "天机化权", "文昌化科", "廉贞化忌"],
                "stars": [[{"name": f"流月星{i+1}", "type": "monthly", "scope": "monthly", "brightness": None, "mutagen": None}] for i in range(12)]
            },
            "daily": {
                "index": 5,
                "name": "流日",
                "heavenlyStem": "丁",
                "earthlyBranch": "巳",
                "palaceNames": palace_names,
                "mutagen": ["天梁化禄", "紫微化权", "太阴化科", "天同化忌"],
                "stars": [[{"name": f"流日星{i+1}", "type": "daily", "scope": "daily", "brightness": None, "mutagen": None}] for i in range(12)]
            },
            "hourly": {
                "index": 7,
                "name": "流时",
                "heavenlyStem": "戊",
                "earthlyBranch": "午",
                "palaceNames": palace_names,
                "mutagen": ["文曲化禄", "廉贞化权", "天相化科", "天梁化忌"],
                "stars": [[{"name": f"流时星{i+1}", "type": "hourly", "scope": "hourly", "brightness": None, "mutagen": None}] for i in range(12)]
            }
        }
                
        logger.info(f"[ZiweiAstro] 已生成紫微斗数模拟数据")
        return result, horoscope

    def ziwei_full_chart_str(self, gender, date_type, date_str, hour_index):
        """
        生成紫微斗数排盘结果字符串
        """
        result, horoscope = self.simulate_astro_result(gender, date_type, date_str, hour_index)
        
        lines = []
        lines.append(f"===== 紫微斗数排盘结果（{date_type} {date_str}，{['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥'][hour_index]}时，{gender}）=====")
        
        # 判断result是py_iztro库的对象还是我们自己的模拟数据
        if hasattr(result, 'solar_date'):
            # 使用py_iztro库的对象
            lines.append(f"命盘公历生日: {result.solar_date}")
            lines.append(f"命盘农历生日: {result.lunar_date}")
            lines.append(f"四柱: {result.chinese_date}")
            lines.append(f"生肖: {result.zodiac}  星座: {result.sign}")
            lines.append(f"命宫: {result.earthly_branch_of_soul_palace}  身宫: {result.earthly_branch_of_body_palace}")
            lines.append(f"命主: {result.soul}  身主: {result.body}")
            lines.append(f"五行局: {result.five_elements_class}")
            lines.append("")
            
            # 输出十二宫位
            for i in range(12):
                palace = result.palaces[i]
                lines.append(
                    f"宫位: {palace.name}\n"
                    f"  干支: {palace.heavenly_stem}{palace.earthly_branch}\n" 
                    f"  主星: {self.format_star_list(palace.major_stars)}\n"
                    f"  辅星: {self.format_star_list(palace.minor_stars)}\n"
                    f"  杂曜: {self.format_star_list(palace.adjective_stars)}\n"
                )
                
                # 添加大运信息
                if hasattr(horoscope, 'decadal') and horoscope.decadal:
                    lines.append(f"  大运: 大运{horoscope.decadal.palace_names[i]}")
                    lines.append(f"    大运星: {self.format_star_list(horoscope.decadal.stars[i])}")
                
                # 添加流年信息
                if hasattr(horoscope, 'yearly') and horoscope.yearly:
                    lines.append(f"  流年: 流年{horoscope.yearly.palace_names[i]}")
                    lines.append(f"    流年星: {self.format_star_list(horoscope.yearly.stars[i])}")
                
                # 添加流月信息
                if hasattr(horoscope, 'monthly') and horoscope.monthly:
                    lines.append(f"  流月: 流月{horoscope.monthly.palace_names[i]}")
                    lines.append(f"    流月星: {self.format_star_list(horoscope.monthly.stars[i])}")
                
                # 添加流日信息
                if hasattr(horoscope, 'daily') and horoscope.daily:
                    lines.append(f"  流日: 流日{horoscope.daily.palace_names[i]}")
                    lines.append(f"    流日星: {self.format_star_list(horoscope.daily.stars[i])}")
                
                # 添加流时信息
                if hasattr(horoscope, 'hourly') and horoscope.hourly:
                    lines.append(f"  流时: 流时{horoscope.hourly.palace_names[i]}")
                    lines.append(f"    流时星: {self.format_star_list(horoscope.hourly.stars[i])}")
        else:
            # 使用模拟数据
        lines.append(f"命盘公历生日: {result.get('solarDate', '')}")
        lines.append(f"命盘农历生日: {result.get('lunarDate', '')}")
        lines.append(f"四柱: {result.get('chineseDate', '')}")
        lines.append(f"生肖: {result.get('zodiac', '')}  星座: {result.get('sign', '')}")
        lines.append(f"命宫: {result.get('earthlyBranchOfSoulPalace', '')}  身宫: {result.get('earthlyBranchOfBodyPalace', '')}")
        lines.append(f"命主: {result.get('soul', '')}  身主: {result.get('body', '')}")
        lines.append(f"五行局: {result.get('fiveElementsClass', '')}")
        lines.append("")
        
        # 输出十二宫位
        for i in range(12):
            palace = result.get('palaces', [])[i] if i < len(result.get('palaces', [])) else None
            if palace:
                lines.append(
                    f"宫位: {palace.get('name', '')}\n"
                    f"  干支: {palace.get('heavenlyStem', '')}{palace.get('earthlyBranch', '')}\n" 
                    f"  主星: {self.format_star_list(palace.get('majorStars', []))}\n"
                    f"  辅星: {self.format_star_list(palace.get('minorStars', []))}\n"
                    f"  杂曜: {self.format_star_list(palace.get('adjectiveStars', []))}\n"
                    f"  大运: 大运{horoscope.get('decadal', {}).get('palaceNames', [])[i] if i < len(horoscope.get('decadal', {}).get('palaceNames', [])) else ''}\n"
                    f"    大运星: {self.format_star_list(horoscope.get('decadal', {}).get('stars', [])[i] if i < len(horoscope.get('decadal', {}).get('stars', [])) else [])}\n"
                    f"  流年: 流年{horoscope.get('yearly', {}).get('palaceNames', [])[i] if i < len(horoscope.get('yearly', {}).get('palaceNames', [])) else ''}\n"
                    f"    流年星: {self.format_star_list(horoscope.get('yearly', {}).get('stars', [])[i] if i < len(horoscope.get('yearly', {}).get('stars', [])) else [])}\n"
                    f"  流月: 流月{horoscope.get('monthly', {}).get('palaceNames', [])[i] if i < len(horoscope.get('monthly', {}).get('palaceNames', [])) else ''}\n"
                    f"    流月星: {self.format_star_list(horoscope.get('monthly', {}).get('stars', [])[i] if i < len(horoscope.get('monthly', {}).get('stars', [])) else [])}\n"
                    f"  流日: 流日{horoscope.get('daily', {}).get('palaceNames', [])[i] if i < len(horoscope.get('daily', {}).get('palaceNames', [])) else ''}\n"
                    f"    流日星: {self.format_star_list(horoscope.get('daily', {}).get('stars', [])[i] if i < len(horoscope.get('daily', {}).get('stars', [])) else [])}\n"
                    f"  流时: 流时{horoscope.get('hourly', {}).get('palaceNames', [])[i] if i < len(horoscope.get('hourly', {}).get('palaceNames', [])) else ''}\n"
                    f"    流时星: {self.format_star_list(horoscope.get('hourly', {}).get('stars', [])[i] if i < len(horoscope.get('hourly', {}).get('stars', [])) else [])}\n"
                )
        
        return '\n'.join(lines)

    def natal_chart_str(self, gender, date_type, date_str, hour_index):
        """仅生成本命盘结果字符串，不包括大运流年等信息"""
        result, _ = self.simulate_astro_result(gender, date_type, date_str, hour_index)
        
        lines = []
        lines.append(f"===== 紫微斗数本命盘（{date_type} {date_str}，{['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥'][hour_index]}时，{gender}）=====")
        
        # 判断result是py_iztro库的对象还是我们自己的模拟数据
        if hasattr(result, 'solar_date'):
            # 使用py_iztro库的对象
            lines.append(f"命盘公历生日: {result.solar_date}")
            lines.append(f"命盘农历生日: {result.lunar_date}")
            lines.append(f"四柱: {result.chinese_date}")
            lines.append(f"生肖: {result.zodiac}  星座: {result.sign}")
            lines.append(f"命宫: {result.earthly_branch_of_soul_palace}  身宫: {result.earthly_branch_of_body_palace}")
            lines.append(f"命主: {result.soul}  身主: {result.body}")
            lines.append(f"五行局: {result.five_elements_class}")
            lines.append("")
            
            # 输出十二宫位基本信息
            for i in range(12):
                palace = result.palaces[i]
                lines.append(
                    f"宫位: {palace.name}\n"
                    f"  干支: {palace.heavenly_stem}{palace.earthly_branch}\n" 
                    f"  主星: {self.format_star_list(palace.major_stars)}\n"
                    f"  辅星: {self.format_star_list(palace.minor_stars)}\n"
                    f"  杂曜: {self.format_star_list(palace.adjective_stars)}\n"
                )
        else:
            # 使用模拟数据
        lines.append(f"命盘公历生日: {result.get('solarDate', '')}")
        lines.append(f"命盘农历生日: {result.get('lunarDate', '')}")
        lines.append(f"四柱: {result.get('chineseDate', '')}")
        lines.append(f"生肖: {result.get('zodiac', '')}  星座: {result.get('sign', '')}")
        lines.append(f"命宫: {result.get('earthlyBranchOfSoulPalace', '')}  身宫: {result.get('earthlyBranchOfBodyPalace', '')}")
        lines.append(f"命主: {result.get('soul', '')}  身主: {result.get('body', '')}")
        lines.append(f"五行局: {result.get('fiveElementsClass', '')}")
        lines.append("")
        
        # 输出十二宫位基本信息
        for i in range(12):
            palace = result.get('palaces', [])[i] if i < len(result.get('palaces', [])) else None
            if palace:
                lines.append(
                    f"宫位: {palace.get('name', '')}\n"
                    f"  干支: {palace.get('heavenlyStem', '')}{palace.get('earthlyBranch', '')}\n" 
                    f"  主星: {self.format_star_list(palace.get('majorStars', []))}\n"
                    f"  辅星: {self.format_star_list(palace.get('minorStars', []))}\n"
                    f"  杂曜: {self.format_star_list(palace.get('adjectiveStars', []))}\n"
                )
        
        return '\n'.join(lines)

    def extract_birth_info(self, text):
        """从用户输入中提取生辰信息"""
        gender = "男"  # 默认为男性
        date_type = "公历"  # 默认为公历
        date_str = ""
        hour_index = 0
        
        # 提取性别
        if re.search(r'[女女性妹子姐姐]', text):
            gender = "女"
        
        # 提取历法类型
        if re.search(r'[农阴]历|阴阳历', text):
            date_type = "农历"
        
        # 提取日期：支持多种格式
        date_patterns = [
            # 标准格式：YYYY年MM月DD日
            r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]',
            # 短横线分隔：YYYY-MM-DD
            r'(\d{4})\s*-\s*(\d{1,2})\s*-\s*(\d{1,2})',
            # 正斜线分隔：YYYY/MM/DD
            r'(\d{4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})',
            # 点号分隔：YYYY.MM.DD
            r'(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})',
            # 简化中文格式，没有"年月日"字符
            r'(\d{4})[年\s]+(\d{1,2})[月\s]+(\d{1,2})[日号\s]*',
            # 纯数字格式，年份在前
            r'(\d{4})(\d{2})(\d{2})',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                year, month, day = match.groups()
                date_str = f"{year}-{month}-{day}"
                logger.info(f"[ZiweiAstro] 从文本中提取到日期: {date_str}")
                break
        
        # 提取时辰 - 支持多种表示方式
        # 1. 传统时辰表示
        traditional_hour_pattern = r'(子|丑|寅|卯|辰|巳|午|未|申|酉|戌|亥)[时辰]'
        match = re.search(traditional_hour_pattern, text)
            if match:
                hour_str = match.group(1)
            hour_index = self.get_hour_index(hour_str)
            logger.info(f"[ZiweiAstro] 从文本中提取到传统时辰: {hour_str}({hour_index})")
        else:
            # 2. 数字小时表示 (24小时制)
            digit_hour_pattern = r'(\d{1,2})[点时:\s]+'
            match = re.search(digit_hour_pattern, text)
            if match:
                hour = int(match.group(1))
                    # 将24小时制转换为12时辰
                    if 23 <= hour or hour < 1:
                        hour_index = 0  # 子时 (23:00-01:00)
                    elif 1 <= hour < 3:
                        hour_index = 1  # 丑时 (01:00-03:00)
                    elif 3 <= hour < 5:
                        hour_index = 2  # 寅时 (03:00-05:00)
                    elif 5 <= hour < 7:
                        hour_index = 3  # 卯时 (05:00-07:00)
                    elif 7 <= hour < 9:
                        hour_index = 4  # 辰时 (07:00-09:00)
                    elif 9 <= hour < 11:
                        hour_index = 5  # 巳时 (09:00-11:00)
                    elif 11 <= hour < 13:
                        hour_index = 6  # 午时 (11:00-13:00)
                    elif 13 <= hour < 15:
                        hour_index = 7  # 未时 (13:00-15:00)
                    elif 15 <= hour < 17:
                        hour_index = 8  # 申时 (15:00-17:00)
                    elif 17 <= hour < 19:
                        hour_index = 9  # 酉时 (17:00-19:00)
                    elif 19 <= hour < 21:
                        hour_index = 10  # 戌时 (19:00-21:00)
                    elif 21 <= hour < 23:
                        hour_index = 11  # 亥时 (21:00-23:00)
                logger.info(f"[ZiweiAstro] 从文本中提取到小时: {hour}({hour_index})")
                else:
                # 3. 时间段表达
                time_periods = {
                    "凌晨": [0, 1, 2, 3, 4, 5],  # 子时、丑时、寅时
                    "早上|早晨|清晨": [5, 6, 7, 8],  # 卯时、辰时
                    "上午": [7, 8, 9, 10, 11],  # 辰时、巳时、午时
                    "中午|正午": [11, 12],  # 午时
                    "下午": [13, 14, 15, 16, 17, 18],  # 未时、申时、酉时
                    "傍晚|黄昏": [17, 18, 19],  # 酉时、戌时开始
                    "晚上|夜晚": [19, 20, 21, 22, 23, 0],  # 戌时、亥时、子时
                    "深夜|午夜": [23, 0, 1, 2, 3],  # 子时、丑时
                }
                
                for period, hours in time_periods.items():
                    if re.search(period, text):
                        # 取该时间段的中间值对应的时辰
                        mid_hour = hours[len(hours) // 2]
                        if 23 <= mid_hour or mid_hour < 1:
                            hour_index = 0  # 子时
                        elif 1 <= mid_hour < 3:
                            hour_index = 1  # 丑时
                        elif 3 <= mid_hour < 5:
                            hour_index = 2  # 寅时
                        elif 5 <= mid_hour < 7:
                            hour_index = 3  # 卯时
                        elif 7 <= mid_hour < 9:
                            hour_index = 4  # 辰时
                        elif 9 <= mid_hour < 11:
                            hour_index = 5  # 巳时
                        elif 11 <= mid_hour < 13:
                            hour_index = 6  # 午时
                        elif 13 <= mid_hour < 15:
                            hour_index = 7  # 未时
                        elif 15 <= mid_hour < 17:
                            hour_index = 8  # 申时
                        elif 17 <= mid_hour < 19:
                            hour_index = 9  # 酉时
                        elif 19 <= mid_hour < 21:
                            hour_index = 10  # 戌时
                        elif 21 <= mid_hour < 23:
                            hour_index = 11  # 亥时
                        logger.info(f"[ZiweiAstro] 从文本中提取到时间段: {period}，对应时辰: {hour_index}")
                break
        
        # 如果没有检测到时辰，默认用午时
        if not date_str:
            logger.warning("[ZiweiAstro] 未能从文本中提取到有效日期")
        
        return gender, date_type, date_str, hour_index

    def on_handle_context(self, e_context: EventContext):
        """处理上下文"""
        if e_context['context'].type != ContextType.TEXT:
            return
            
        content = e_context['context'].content
        logger.debug(f"[ZiweiAstro] 收到文本消息: {content}")
        
        # 获取用户ID
        msg = e_context['context'].get('msg', None)
        if not msg:
            return
        
        user_id = msg.from_user_id
        
        # 检查是否是安装依赖的请求
        install_keywords = ["安装紫薇斗数依赖", "安装紫微斗数依赖", "安装py_iztro", "安装依赖"]
        if any(keyword in content for keyword in install_keywords):
            logger.info("[ZiweiAstro] 检测到安装依赖请求")
            result = self.install_dependencies()
                reply = Reply()
                reply.type = ReplyType.TEXT
            reply.content = result
                e_context['reply'] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
        # 检查用户状态，处理确认流程
        if user_id in self.user_states:
            # 用户处于确认流程中
            user_state = self.user_states[user_id]
            
            # 判断用户是否取消确认流程
            if any(word in content for word in ["取消", "停止", "不要了", "算了"]):
                del self.user_states[user_id]
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = "已取消紫薇斗数排盘。"
                e_context['reply'] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
            # 处理不同确认阶段
            if user_state["stage"] == "confirm_gender":
                # 确认性别
                if "男" in content:
                    user_state["gender"] = "男"
                    user_state["stage"] = "confirm_date_type"
                    prompt = f"您的性别已确认为【男】。\n\n请确认您的出生日期是农历还是公历？(回复'农历'或'公历')"
                elif "女" in content:
                    user_state["gender"] = "女"
                    user_state["stage"] = "confirm_date_type"
                    prompt = f"您的性别已确认为【女】。\n\n请确认您的出生日期是农历还是公历？(回复'农历'或'公历')"
                else:
                    prompt = "请明确告诉我您的性别是男还是女？"
                    
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = prompt
                e_context['reply'] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
            elif user_state["stage"] == "confirm_date_type":
                # 确认历法类型
                if "农历" in content or "阴历" in content:
                    user_state["date_type"] = "农历"
                    user_state["stage"] = "confirm_date"
                    prompt = f"您的历法已确认为【农历】。\n\n请确认您的出生日期是：{user_state['date_str']}？(回复'是'确认，或直接输入正确的日期)"
                elif "公历" in content or "阳历" in content:
                    user_state["date_type"] = "公历"
                    user_state["stage"] = "confirm_date"
                    prompt = f"您的历法已确认为【公历】。\n\n请确认您的出生日期是：{user_state['date_str']}？(回复'是'确认，或直接输入正确的日期)"
                else:
                    prompt = "请明确告诉我您的出生日期是农历还是公历？"
                    
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = prompt
                e_context['reply'] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
            elif user_state["stage"] == "confirm_date":
                # 确认出生日期
                if any(word in content for word in ["是", "对", "确认", "正确", "没错", "yes", "确定"]):
                    user_state["stage"] = "confirm_hour"
                    hour_names = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
                    hour_name = hour_names[user_state["hour_index"]]
                    prompt = f"您的出生日期已确认为【{user_state['date_str']}】。\n\n请确认您的出生时辰是：{hour_name}时(约{user_state['hour_index']*2}-{(user_state['hour_index']+1)*2}点)？(回复'是'确认，或直接输入正确的时辰)"
                else:
                    # 尝试从用户输入中提取新的日期
                    import re
                    date_patterns = [
                        r'(\d{4})[-\/\.](\d{1,2})[-\/\.](\d{1,2})',  # 匹配 YYYY-MM-DD 或 YYYY/MM/DD 或 YYYY.MM.DD
                        r'(\d{4})[年\s]+(\d{1,2})[月\s]+(\d{1,2})[日号\s]*',  # 匹配 YYYY年MM月DD日
                    ]
                    
                    matched = False
                    for pattern in date_patterns:
                        match = re.search(pattern, content)
                        if match:
                            year, month, day = match.groups()
                            user_state["date_str"] = f"{year}-{month}-{day}"
                            matched = True
                            break
                    
                    if matched:
                        user_state["stage"] = "confirm_hour"
                        hour_names = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
                        hour_name = hour_names[user_state["hour_index"]]
                        prompt = f"您的出生日期已更新为【{user_state['date_str']}】。\n\n请确认您的出生时辰是：{hour_name}时(约{user_state['hour_index']*2}-{(user_state['hour_index']+1)*2}点)？(回复'是'确认，或直接输入正确的时辰)"
                    else:
                        prompt = "无法识别您输入的日期格式，请按照'YYYY-MM-DD'或'YYYY年MM月DD日'的格式输入，例如'1990-1-1'或'1990年1月1日'。"
                    
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = prompt
                e_context['reply'] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
            elif user_state["stage"] == "confirm_hour":
                # 确认出生时辰
                hour_names = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
                hour_name = hour_names[user_state["hour_index"]]
                
                if any(word in content for word in ["是", "对", "确认", "正确", "没错", "yes", "确定"]):
                    user_state["stage"] = "final_confirm"
                    
                    # 生成最终确认信息
                    gender = user_state["gender"]
                    date_type = user_state["date_type"]
                    date_str = user_state["date_str"]
                    hour_name = hour_names[user_state["hour_index"]]
                    
                    prompt = f"请确认以下紫薇排盘信息：\n\n性别：{gender}\n历法：{date_type}\n出生日期：{date_str}\n出生时辰：{hour_name}时\n\n信息无误请回复'确认排盘'，如需修改请回复'重新输入'。"
                elif any(char in content for char in ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]):
                    # 直接匹配十二地支
                    for idx, name in enumerate(hour_names):
                        if name in content:
                            user_state["hour_index"] = idx
                            break
                    
                    user_state["stage"] = "final_confirm"
                    
                    # 生成最终确认信息
                    gender = user_state["gender"]
                    date_type = user_state["date_type"]
                    date_str = user_state["date_str"]
                    hour_name = hour_names[user_state["hour_index"]]
                    
                    prompt = f"您的出生时辰已更新为【{hour_name}时】。\n\n请确认以下紫薇排盘信息：\n\n性别：{gender}\n历法：{date_type}\n出生日期：{date_str}\n出生时辰：{hour_name}时\n\n信息无误请回复'确认排盘'，如需修改请回复'重新输入'。"
                elif re.search(r'(\d{1,2})[点时:\s]', content):
                    # 处理小时格式
                    match = re.search(r'(\d{1,2})[点时:\s]', content)
                    hour = int(match.group(1))
                    # 将24小时制转换为12时辰
                    if 23 <= hour or hour < 1:
                        hour_index = 0  # 子时 (23:00-01:00)
                    elif 1 <= hour < 3:
                        hour_index = 1  # 丑时 (01:00-03:00)
                    elif 3 <= hour < 5:
                        hour_index = 2  # 寅时 (03:00-05:00)
                    elif 5 <= hour < 7:
                        hour_index = 3  # 卯时 (05:00-07:00)
                    elif 7 <= hour < 9:
                        hour_index = 4  # 辰时 (07:00-09:00)
                    elif 9 <= hour < 11:
                        hour_index = 5  # 巳时 (09:00-11:00)
                    elif 11 <= hour < 13:
                        hour_index = 6  # 午时 (11:00-13:00)
                    elif 13 <= hour < 15:
                        hour_index = 7  # 未时 (13:00-15:00)
                    elif 15 <= hour < 17:
                        hour_index = 8  # 申时 (15:00-17:00)
                    elif 17 <= hour < 19:
                        hour_index = 9  # 酉时 (17:00-19:00)
                    elif 19 <= hour < 21:
                        hour_index = 10  # 戌时 (19:00-21:00)
                    elif 21 <= hour < 23:
                        hour_index = 11  # 亥时 (21:00-23:00)
                    
                    user_state["hour_index"] = hour_index
                    hour_name = hour_names[hour_index]
                    
                    user_state["stage"] = "final_confirm"
                    
                    # 生成最终确认信息
                    gender = user_state["gender"]
                    date_type = user_state["date_type"]
                    date_str = user_state["date_str"]
                    
                    prompt = f"您的出生时辰已更新为【{hour_name}时】（相当于{hour}点）。\n\n请确认以下紫薇排盘信息：\n\n性别：{gender}\n历法：{date_type}\n出生日期：{date_str}\n出生时辰：{hour_name}时\n\n信息无误请回复'确认排盘'，如需修改请回复'重新输入'。"
                else:
                    prompt = f"无法识别您输入的时辰格式。请使用十二地支（子、丑、寅、卯、辰、巳、午、未、申、酉、戌、亥）或小时数（0-23点）表示时辰。\n您当前的时辰是【{hour_name}时】，是否确认？"
                
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = prompt
                e_context['reply'] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
            elif user_state["stage"] == "final_confirm":
                # 最终确认
                if "确认排盘" in content or any(word in content for word in ["确认", "是", "对", "没错", "开始排盘"]):
                    # 提取信息进行排盘
                    gender = user_state["gender"]
                    date_type = user_state["date_type"]
                    date_str = user_state["date_str"]
                    hour_index = user_state["hour_index"]
                    needs_interpretation = user_state.get("needs_interpretation", False)
                    
                    # 清理状态
                    del self.user_states[user_id]
                    
                    # 存储用户生辰八字信息到会话上下文中
                    # 将生辰八字信息添加到DeepSeek的会话上下文
                    try:
                        # 提示用户生辰八字信息已记录
                        hour_names = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
                        birth_info_summary = f"用户信息：{gender}，{date_type}生日{date_str}，{hour_names[hour_index]}时"
                        
                        # 获取会话ID
                        session_id = e_context['context'].get('session_id')
                        if not session_id:
                            session_id = f"user_{user_id}"
                        
                        # 构造一个特殊消息传给DeepSeek，这会被记录在会话历史中
                        system_prompt = f"[系统信息] 已记录用户生辰八字信息：{gender}，{date_type}生日{date_str}，{hour_names[hour_index]}时。请在用户询问时使用这些信息。"
                        
                        # 将提示添加到当前上下文，让下游处理
                        e_context['context'].content += f"\n\n{system_prompt}"
                        
                        # 将生辰八字信息保存到用户数据中，以便后续使用
                        user_data = conf().get_user_data(user_id)
                        if not user_data:
                            user_data = {}
                        
                        user_data["birth_info"] = {
                            "gender": gender,
                            "date_type": date_type,
                            "date_str": date_str,
                            "hour_index": hour_index,
                            "recorded_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        conf().set_user_data(user_id, user_data)
                        logger.info(f"[ZiweiAstro] 已将用户 {user_id} 的生辰八字信息保存到用户数据")
                    except Exception as e:
                        logger.error(f"[ZiweiAstro] 保存生辰八字信息到会话上下文时出错: {e}")
            
            # 生成相应的排盘结果
            chart_str = ""
                    if user_state.get("is_natal_only", False):
                chart_str = self.natal_chart_str(gender, date_type, date_str, hour_index)
                chart_type = "本命盘"
            else:
                # 根据用户意图生成不同级别的排盘结果
                chart_str = self.generate_custom_chart(gender, date_type, date_str, hour_index, 
                                                              include_decadal=True, include_yearly=True, 
                                                              include_monthly=True, include_daily=True, include_hourly=True)
                        chart_type = "完整命盘"
                    
                    # 发送排盘结果
            reply = Reply()
            reply.type = ReplyType.TEXT
            reply.content = chart_str
            e_context['reply'] = reply
                    e_context.action = EventAction.BREAK_PASS
            
                    # 如果需要解读，在返回排盘结果后，自动触发解读过程
            if needs_interpretation:
                    # 设置会话上下文，用于后续解读
                    user_context = {
                        "chart_str": chart_str,
                        "chart_type": chart_type,
                        "gender": gender,
                        "date_type": date_type,
                        "date_str": date_str,
                        "hour_index": hour_index,
                        "needs_interpretation": True
                    }
                    
                    # 将用户上下文信息存入用户数据
                    user_data = conf().get_user_data(user_id)
                    if not user_data:
                        user_data = {}
                    user_data["ziwei_context"] = user_context
                    conf().set_user_data(user_id, user_data)
                    
                        # 创建一个解读任务，使用大模型进行解读
                        self.process_interpretation_async(user_id, chart_str, chart_type, e_context['context'].ctype, msg)
                    
                    return
                elif "重新输入" in content:
                    # 清理状态，重新开始
                    del self.user_states[user_id]
                    
                    reply = Reply()
                    reply.type = ReplyType.TEXT
                    reply.content = "已重置信息，请重新输入您的生辰八字，例如：紫薇排盘 1990年1月1日"
                    e_context['reply'] = reply
                    e_context.action = EventAction.BREAK_PASS
                    return
                else:
                    reply = Reply()
                    reply.type = ReplyType.TEXT
                    reply.content = "请回复'确认排盘'进行排盘，或回复'重新输入'重置信息。"
                    e_context['reply'] = reply
                    e_context.action = EventAction.BREAK_PASS
                    return
            
            return
        
        # 增强对紫薇排盘相关意图的识别
        ziwei_keywords = ["紫薇排盘", "紫微排盘", "紫薇命盘", "紫微命盘", "紫微斗数", "紫薇斗数"]
        bazi_keywords = ["八字", "生辰八字"]
        action_keywords = ["排盘", "命盘", "解读", "分析", "解析"]
        
        has_ziwei_intent = any(keyword in content for keyword in ziwei_keywords)
        has_bazi_intent = any(keyword in content for keyword in bazi_keywords) and any(keyword in content for keyword in action_keywords)
        
        # 识别生辰八字信息
        has_birth_info = (
            re.search(r'(\d{4})[年\-\/\.]', content) is not None  # 包含年份
            or any(word in content for word in ["子时", "丑时", "寅时", "卯时", "辰时", "巳时", "午时", "未时", "申时", "酉时", "戌时", "亥时"])  # 包含时辰
        )
        
        # 检查是否要获取已保存的生辰八字信息
        birth_info_query_keywords = ["我的生辰八字", "我的八字", "我的星盘", "我的命盘"]
        is_birth_info_query = any(keyword in content for keyword in birth_info_query_keywords)
        
        if is_birth_info_query:
            # 查询用户是否有保存的生辰八字信息
            user_data = conf().get_user_data(user_id)
            if user_data and "birth_info" in user_data:
                birth_info = user_data["birth_info"]
                hour_names = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
                
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = f"您之前提供的生辰八字信息是：\n\n性别：{birth_info['gender']}\n历法：{birth_info['date_type']}\n日期：{birth_info['date_str']}\n时辰：{hour_names[birth_info['hour_index']]}时\n\n记录时间：{birth_info.get('recorded_time', '未知')}"
                
                e_context['reply'] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            else:
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = "您尚未提供过生辰八字信息，请发送您的生辰八字以便为您排盘。"
                
                e_context['reply'] = reply
                e_context.action = EventAction.BREAK_PASS
                return
        
        if has_ziwei_intent or has_bazi_intent or has_birth_info:
            logger.info("[ZiweiAstro] 检测到紫薇排盘相关意图")
            
            # 解析生辰信息
            gender, date_type, date_str, hour_index = self.extract_birth_info(content)
            
            # 检查是否提取到日期信息
            if not date_str:
                # 如果没有提取到足够的信息，询问用户
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = "我注意到您似乎对紫薇斗数排盘感兴趣，但没有提供完整的生辰八字信息。请提供您的出生年月日和时辰，例如：1990年1月1日子时"
                e_context['reply'] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
            # 判断是否需要解读
            needs_interpretation = any(keyword in content for keyword in ["解读", "分析", "解释", "求解", "批解", "批命", "解析"])
            
            # 判断是查看本命盘还是完整盘
            is_natal_only = "本命" in content and not any(word in content for word in ["大运", "流年", "流月", "流日", "流时"])
            
            # 初始化用户状态
            self.user_states[user_id] = {
                "stage": "confirm_gender",  # 开始确认性别
                "gender": gender,
                "date_type": date_type,
                "date_str": date_str,
                "hour_index": hour_index,
                "needs_interpretation": needs_interpretation,
                "is_natal_only": is_natal_only
            }
            
            # 生成回复，询问用户确认性别
            reply = Reply()
            reply.type = ReplyType.TEXT
            reply.content = f"我将为您进行紫薇斗数排盘，请确认您的信息：\n\n首先，您的性别是男还是女？(回复'男'或'女')"
            e_context['reply'] = reply
            e_context.action = EventAction.BREAK_PASS
            return
        
        # 检查是否需要继续之前的解读
        elif any(phrase in content for phrase in ["继续解读", "接着解读", "继续分析", "接着分析", "更多解读", "详细解读"]):
            # 获取用户信息
                user_data = conf().get_user_data(user_id)
                if user_data and "ziwei_context" in user_data:
                    ziwei_context = user_data["ziwei_context"]
                    if ziwei_context.get("needs_interpretation", False):
                    # 回复用户，告知正在继续解读
                    reply = Reply()
                    reply.type = ReplyType.TEXT
                    reply.content = "月下星官正在为你继续解读命盘玄机..."
                    e_context['reply'] = reply
                    e_context.action = EventAction.BREAK_PASS
                    
                    # 创建继续解读的提示词
                    prompt = f"继续解读之前的紫微斗数{ziwei_context['chart_type']}，提供更多关于运势、性格、事业、财运、婚姻等方面的详细信息："
                    
                    # 调用异步处理
                    self.process_continued_interpretation_async(user_id, ziwei_context['chart_type'], prompt, e_context['context'].ctype, msg)
                        return
            
            # 如果没有找到上下文信息
            reply = Reply()
            reply.type = ReplyType.TEXT
            reply.content = "抱歉，没有找到您之前的紫薇命盘信息，请先提供生辰八字进行排盘。"
            e_context['reply'] = reply
            e_context.action = EventAction.BREAK_PASS
            return

    def process_interpretation_async(self, user_id, chart_str, chart_type, ctype, orig_msg):
        """处理排盘解读，保持在同一个对话线程中"""
        try:
            # 创建解读提示词 - 使用月下星官角色设定
            prompt_template = f"""
我现在希望你扮演一个专业的紫微斗数预测师，以"月下星官"的角色解读以下{chart_type}结果。
请基于命盘中的所有信息，进行系统性的解读，体现出专业的紫微斗数知识，让客户理解命盘中的含义。
请使用第一人称，仿佛你是一位优雅神秘的月下星官，带着夜空星辰的气息，温柔细致地为客户分析。

使用你的敬语与恭维，以"阁下"、"看官"或"缘主"称呼对方。
偶尔穿插几句古风雅言，如"天机玄妙"、"命格非凡"、"气运流转"等，展现出你的不凡气质。
在解读过程中，请引用《渊海子平》、《穷通宝鉴》等古籍中的原文，增加解读的权威性。
结尾处可以提到"星辰变幻，命格可转"，暗示虽有定数但人定胜天的积极思想。

{chart_str}

请根据以上命盘信息，进行全面详细的解读，包括但不限于：
1. 命主的个性特点、天赋才能
2. 事业发展、职业选择
3. 财富状况
4. 婚姻与情感
5. 家庭关系
6. 健康状况
7. 学业发展
8. 人际关系
9. 未来运势走向

注意：这是一个严肃的紫微斗数解读，请保持专业性，同时融入你的月下星官角色，展现深厚的星象知识和优雅神秘的气质。
"""
            
            # 从配置中获取对话模型信息
            from config import conf
            from common.log import logger
            
            # 导入必要的模块
            import asyncio
            from bridge.reply import Reply, ReplyType
            
            # 使用MessageManager直接向DeepSeek发送请求
            # 这样会保持在同一个对话线程中
            from common.utils import send_message_to_open_ai_with_retry
            
            async def process_interpretation():
                try:
                    # 等待0.5秒，确保排盘结果已经发送
                    await asyncio.sleep(0.5)
                    
                    # 发送解读请求
                    logger.info(f"[ZiweiAstro] 发送紫微命盘解读请求: {user_id}")
                    
                    # 构建回复消息
                    reply = Reply()
                    reply.type = ReplyType.TEXT
                    
                    # 使用DeepSeek API直接获取回复
                    model = conf().get("model")
                    api_key = conf().get("open_ai_api_key")
                    base_url = conf().get("open_ai_api_base")
                    temperature = conf().get("temperature", 0.7)
                    top_p = conf().get("top_p", 0.9)
                    
                    # 直接调用DeepSeek API获取解读结果
                    result = await send_message_to_open_ai_with_retry(
                        prompt_template,
                        model=model,
                        api_key=api_key,
                        base_url=base_url,
                        temperature=temperature,
                        top_p=top_p
                    )
                    
                    if result:
                        reply.content = f"【月下星官·紫微命盘解读】\n\n{result}"
                        
                        # 发送解读结果
                        from common.utils import send_reply
                        await send_reply(reply, orig_msg)
                        logger.info(f"[ZiweiAstro] 紫微命盘解读已发送: {user_id}")
                    else:
                        logger.error(f"[ZiweiAstro] 紫微命盘解读请求失败")
                except Exception as e:
                    logger.error(f"[ZiweiAstro] 处理解读任务时出错: {e}")
                    import traceback
                    logger.error(f"[ZiweiAstro] 异常堆栈: {traceback.format_exc()}")
            
            # 启动异步任务
            if hasattr(self, 'asyncio_available') and self.asyncio_available:
                asyncio.create_task(process_interpretation())
            else:
                # 回退方案：使用线程
                import threading
                thread = threading.Thread(target=lambda: asyncio.run(process_interpretation()))
                thread.daemon = True
                thread.start()
        except Exception as e:
            logger.error(f"[ZiweiAstro] 启动解读任务时出错: {e}")
            import traceback
            logger.error(f"[ZiweiAstro] 异常堆栈: {traceback.format_exc()}")

    def process_continued_interpretation_async(self, user_id, chart_type, prompt, ctype, orig_msg):
        """处理继续解读，保持在同一个对话线程中"""
        try:
            # 从配置中获取对话模型信息
            from config import conf
            from common.log import logger
            
            # 导入必要的模块
            import asyncio
            from bridge.reply import Reply, ReplyType
            
            # 使用MessageManager直接向DeepSeek发送请求
            # 这样会保持在同一个对话线程中
            from common.utils import send_message_to_open_ai_with_retry
            
            # 构建提示词，保持月下星官角色
            full_prompt = f"""
我希望你继续扮演专业的紫微斗数预测师"月下星官"的角色，解答以下关于{chart_type}的问题：

{prompt}

请保持你优雅神秘的月下星官身份，使用敬语与古风表达，带着夜空星辰的气息回应提问。
记得引用古籍中的原文增加权威性，并在回答中展现你深厚的紫微斗数专业知识。
"""
            
            async def process_continued_interpretation():
                try:
                    # 等待0.5秒，确保上一条消息已经发送
                    await asyncio.sleep(0.5)
                    
                    # 发送继续解读请求
                    logger.info(f"[ZiweiAstro] 发送紫微命盘继续解读请求: {user_id}")
                    
                    # 构建回复消息
                    reply = Reply()
                    reply.type = ReplyType.TEXT
                    
                    # 使用DeepSeek API直接获取回复
                    model = conf().get("model")
                    api_key = conf().get("open_ai_api_key")
                    base_url = conf().get("open_ai_api_base")
                    temperature = conf().get("temperature", 0.7)
                    top_p = conf().get("top_p", 0.9)
                    
                    # 直接调用DeepSeek API获取解读结果
                    result = await send_message_to_open_ai_with_retry(
                        full_prompt,
                        model=model,
                        api_key=api_key,
                        base_url=base_url,
                        temperature=temperature,
                        top_p=top_p
                    )
                    
                    if result:
                        reply.content = f"【月下星官·补充解读】\n\n{result}"
                        
                        # 发送解读结果
                        from common.utils import send_reply
                        await send_reply(reply, orig_msg)
                        logger.info(f"[ZiweiAstro] 紫微命盘补充解读已发送: {user_id}")
                    else:
                        logger.error(f"[ZiweiAstro] 紫微命盘补充解读请求失败")
                except Exception as e:
                    logger.error(f"[ZiweiAstro] 处理补充解读任务时出错: {e}")
                    import traceback
                    logger.error(f"[ZiweiAstro] 异常堆栈: {traceback.format_exc()}")
            
            # 启动异步任务
            if hasattr(self, 'asyncio_available') and self.asyncio_available:
                asyncio.create_task(process_continued_interpretation())
            else:
                # 回退方案：使用线程
                import threading
                thread = threading.Thread(target=lambda: asyncio.run(process_continued_interpretation()))
                thread.daemon = True
                thread.start()
        except Exception as e:
            logger.error(f"[ZiweiAstro] 启动补充解读任务时出错: {e}")
            import traceback
            logger.error(f"[ZiweiAstro] 异常堆栈: {traceback.format_exc()}")

    def generate_custom_chart(self, gender, date_type, date_str, hour_index, 
                             include_decadal=True, include_yearly=True, 
                             include_monthly=True, include_daily=True, include_hourly=True):
        """
        根据用户需求生成定制的排盘结果
        """
        result, horoscope = self.simulate_astro_result(gender, date_type, date_str, hour_index)
        
        lines = []
        hour_names = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
        lines.append(f"===== 紫微斗数{'' if all([include_decadal, include_yearly]) else '定制'}排盘结果（{date_type} {date_str}，{hour_names[hour_index]}时，{gender}）=====")
        
        # 判断result是py_iztro库的对象还是我们自己的模拟数据
        if hasattr(result, 'solar_date'):
            # 使用py_iztro库的对象
            lines.append(f"命盘公历生日: {result.solar_date}")
            lines.append(f"命盘农历生日: {result.lunar_date}")
            lines.append(f"四柱: {result.chinese_date}")
            lines.append(f"生肖: {result.zodiac}  星座: {result.sign}")
            lines.append(f"命宫: {result.earthly_branch_of_soul_palace}  身宫: {result.earthly_branch_of_body_palace}")
            lines.append(f"命主: {result.soul}  身主: {result.body}")
            lines.append(f"五行局: {result.five_elements_class}")
            lines.append("")
            
            # 输出十二宫位
            for i in range(12):
                palace = result.palaces[i]
                palace_lines = [
                    f"宫位: {palace.name}",
                    f"  干支: {palace.heavenly_stem}{palace.earthly_branch}",
                    f"  主星: {self.format_star_list(palace.major_stars)}",
                    f"  辅星: {self.format_star_list(palace.minor_stars)}",
                    f"  杂曜: {self.format_star_list(palace.adjective_stars)}"
                ]
                
                # 添加大运信息
                if include_decadal and hasattr(horoscope, 'decadal') and horoscope.decadal:
                    palace_lines.append(f"  大运: 大运{horoscope.decadal.palace_names[i]}")
                    palace_lines.append(f"    大运星: {self.format_star_list(horoscope.decadal.stars[i])}")
                
                # 添加流年信息
                if include_yearly and hasattr(horoscope, 'yearly') and horoscope.yearly:
                    palace_lines.append(f"  流年: 流年{horoscope.yearly.palace_names[i]}")
                    palace_lines.append(f"    流年星: {self.format_star_list(horoscope.yearly.stars[i])}")
                
                # 添加流月信息
                if include_monthly and hasattr(horoscope, 'monthly') and horoscope.monthly:
                    palace_lines.append(f"  流月: 流月{horoscope.monthly.palace_names[i]}")
                    palace_lines.append(f"    流月星: {self.format_star_list(horoscope.monthly.stars[i])}")
                
                # 添加流日信息
                if include_daily and hasattr(horoscope, 'daily') and horoscope.daily:
                    palace_lines.append(f"  流日: 流日{horoscope.daily.palace_names[i]}")
                    palace_lines.append(f"    流日星: {self.format_star_list(horoscope.daily.stars[i])}")
                
                # 添加流时信息
                if include_hourly and hasattr(horoscope, 'hourly') and horoscope.hourly:
                    palace_lines.append(f"  流时: 流时{horoscope.hourly.palace_names[i]}")
                    palace_lines.append(f"    流时星: {self.format_star_list(horoscope.hourly.stars[i])}")
                
                lines.append("\n".join(palace_lines))
            
        else:
            # 使用模拟数据
        lines.append(f"命盘公历生日: {result.get('solarDate', '')}")
        lines.append(f"命盘农历生日: {result.get('lunarDate', '')}")
        lines.append(f"四柱: {result.get('chineseDate', '')}")
        lines.append(f"生肖: {result.get('zodiac', '')}  星座: {result.get('sign', '')}")
        lines.append(f"命宫: {result.get('earthlyBranchOfSoulPalace', '')}  身宫: {result.get('earthlyBranchOfBodyPalace', '')}")
        lines.append(f"命主: {result.get('soul', '')}  身主: {result.get('body', '')}")
        lines.append(f"五行局: {result.get('fiveElementsClass', '')}")
        lines.append("")
        
        # 输出十二宫位
        for i in range(12):
            palace = result.get('palaces', [])[i] if i < len(result.get('palaces', [])) else None
            if palace:
                palace_lines = [
                        f"宫位: {palace.get('name', '')}",
                        f"  干支: {palace.get('heavenlyStem', '')}{palace.get('earthlyBranch', '')}",
                        f"  主星: {self.format_star_list(palace.get('majorStars', []))}",
                        f"  辅星: {self.format_star_list(palace.get('minorStars', []))}",
                    f"  杂曜: {self.format_star_list(palace.get('adjectiveStars', []))}"
                ]
                
                    # 添加大运信息
                if include_decadal:
                    palace_lines.append(f"  大运: 大运{horoscope.get('decadal', {}).get('palaceNames', [])[i] if i < len(horoscope.get('decadal', {}).get('palaceNames', [])) else ''}")
                    palace_lines.append(f"    大运星: {self.format_star_list(horoscope.get('decadal', {}).get('stars', [])[i] if i < len(horoscope.get('decadal', {}).get('stars', [])) else [])}")
                    
                    # 添加流年信息
                if include_yearly:
                    palace_lines.append(f"  流年: 流年{horoscope.get('yearly', {}).get('palaceNames', [])[i] if i < len(horoscope.get('yearly', {}).get('palaceNames', [])) else ''}")
                    palace_lines.append(f"    流年星: {self.format_star_list(horoscope.get('yearly', {}).get('stars', [])[i] if i < len(horoscope.get('yearly', {}).get('stars', [])) else [])}")
                    
                    # 添加流月信息
                if include_monthly:
                    palace_lines.append(f"  流月: 流月{horoscope.get('monthly', {}).get('palaceNames', [])[i] if i < len(horoscope.get('monthly', {}).get('palaceNames', [])) else ''}")
                    palace_lines.append(f"    流月星: {self.format_star_list(horoscope.get('monthly', {}).get('stars', [])[i] if i < len(horoscope.get('monthly', {}).get('stars', [])) else [])}")
                    
                    # 添加流日信息
                if include_daily:
                    palace_lines.append(f"  流日: 流日{horoscope.get('daily', {}).get('palaceNames', [])[i] if i < len(horoscope.get('daily', {}).get('palaceNames', [])) else ''}")
                    palace_lines.append(f"    流日星: {self.format_star_list(horoscope.get('daily', {}).get('stars', [])[i] if i < len(horoscope.get('daily', {}).get('stars', [])) else [])}")
                    
                    # 添加流时信息
                if include_hourly:
                    palace_lines.append(f"  流时: 流时{horoscope.get('hourly', {}).get('palaceNames', [])[i] if i < len(horoscope.get('hourly', {}).get('palaceNames', [])) else ''}")
                    palace_lines.append(f"    流时星: {self.format_star_list(horoscope.get('hourly', {}).get('stars', [])[i] if i < len(horoscope.get('hourly', {}).get('stars', [])) else [])}")
                
                lines.append("\n".join(palace_lines))
        
        return '\n'.join(lines)

    def get_help_text(self, **kwargs):
        help_text = "紫薇斗数排盘插件使用说明：\n"
        help_text += "示例1：紫薇排盘 公历1990年1月1日子时 男\n"
        help_text += "示例2：紫薇排盘 农历1990年1月1日午时 女\n"
        help_text += "示例3：请帮我解读公历1990-1-1子时男生的紫薇命盘\n"
        help_text += "示例4：我想查看本命盘，公历1990年1月1日寅时男\n"
        help_text += "示例5：继续解读（获取之前命盘的进一步解读）\n\n"
        help_text += "支持公历/农历，支持年-月-日或年月日格式，支持十二地支时辰或24小时制\n\n"
        
        # 显示py_iztro库状态
        if hasattr(self, 'py_iztro_available'):
            if self.py_iztro_available:
                help_text += "状态：已安装py_iztro库，使用真实计算引擎\n"
            else:
                help_text += "状态：未安装py_iztro库，使用模拟数据（可发送"安装紫薇斗数依赖"进行安装）\n"
        
        return help_text 

    def install_dependencies(self):
        """安装紫薇斗数排盘所需的依赖库"""
        import subprocess
        import sys
        
        try:
            logger.info("[ZiweiAstro] 开始安装py_iztro库...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "py-iztro"])
            
            # 重新导入库检查是否安装成功
            try:
                import py_iztro
                self.py_iztro_available = True
                logger.info("[ZiweiAstro] py_iztro库安装成功")
                return "py_iztro库安装成功！现在可以使用真实的紫微斗数排盘引擎了。"
            except ImportError:
                self.py_iztro_available = False
                logger.error("[ZiweiAstro] py_iztro库安装后仍无法导入")
                return "py_iztro库安装失败，请尝试手动安装: pip install py-iztro"
        except Exception as e:
            logger.error(f"[ZiweiAstro] 安装py_iztro库时出错: {e}")
            return f"安装py_iztro库时出错: {e}，请尝试手动安装: pip install py-iztro" 
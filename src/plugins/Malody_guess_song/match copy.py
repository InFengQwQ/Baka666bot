# match.py
import re
from typing import Optional

from rapidfuzz import fuzz
import zhconv
from unidecode import unidecode

# 全角字母数字转半角
_FULL_TO_HALF = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)


# ========== 新增：片假名 → 形近汉字映射表 ==========
_KANA_TO_CJK = {
    # 清音
    'ア': '了', 'イ': '亻', 'ウ': '宀', 'エ': '工', 'オ': '才',
    'カ': '力', 'キ': '丰', 'ク': '久', 'ケ': '个', 'コ': '己',
    'サ': '艹', 'シ': '氵', 'ス': '又', 'セ': '世', 'ソ': '冫',
    'タ': '夕', 'チ': '千', 'ツ': '川', 'テ': '天', 'ト': '卜',
    'ナ': '十', 'ニ': '二', 'ヌ': '又', 'ネ': '礻', 'ノ': '丿',
    'ハ': '八', 'ヒ': '匕', 'フ': '乛', 'ヘ': '乀', 'ホ': '木',
    'マ': '末', 'ミ': '三', 'ム': '厶', 'メ': '乂', 'モ': '毛',
    'ヤ': '也', 'ユ': '由', 'ヨ': '彐',
    'ラ': '了', 'リ': '刂', 'ル': '儿', 'レ': '乚', 'ロ': '口',
    'ワ': '冖', 'ヲ': '丂', 'ン': '二',
    # 浊音（例：ガ＝力）
    'ガ': '力', 'ギ': '丰', 'グ': '久', 'ゲ': '个', 'ゴ': '己',
    'ザ': '艹', 'ジ': '氵', 'ズ': '又', 'ゼ': '世', 'ゾ': '冫',
    'ダ': '夕', 'ヂ': '千', 'ヅ': '川', 'デ': '天', 'ド': '卜',
    'バ': '八', 'ビ': '匕', 'ブ': '乛', 'ベ': '乀', 'ボ': '术',  # ホ゜＝术
    # 半浊音
    'パ': '八', 'ピ': '匕', 'プ': '乛', 'ペ': '乀', 'ポ': '术',
    # 小写假名（拗音等）
    'ァ': '了', 'ィ': '亻', 'ゥ': '宀', 'ェ': '工', 'ォ': '才',
    'ッ': '川', 'ャ': '也', 'ュ': '由', 'ョ': '彐',
    # 长音符号
    'ー': '一',
}

def _normalize(text: str) -> str:
    """清洗文本：全角转半角，转写扩展拉丁字符，去括号，替换形近假名，保留字母数字汉字假名空格"""
    text = text.translate(_FULL_TO_HALF)
    text = unidecode(text)
    # 替换假名为形近汉字
    text = ''.join(_KANA_TO_CJK.get(c, c) for c in text)
    # 去除各种括号内容
    text = re.sub(r'[（(].*?[）)]', '', text)
    text = re.sub(r'[【「『].*?[】」』]', '', text)
    text = re.sub(r'[\[].*?[\]]', '', text)
    text = re.sub(r'[\{].*?[\}]', '', text)
    # 保留字母数字、中日韩统一汉字及假名（假名已被替换为汉字，不再特殊保留）
    text = re.sub(r'[^\w\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u309f\u30a0-\u30ff ]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text.lower()


def _extract_han(text: str) -> str:
    """提取汉字序列，统一转换为简体（兼容简繁日汉字）"""
    han_pattern = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]')
    hans = han_pattern.findall(text)
    if not hans:
        return ''
    return zhconv.convert(''.join(hans), 'zh-cn')


def _extract_digits(text: str) -> str:
    """提取所有数字字符，保持原有顺序"""
    return ''.join(re.findall(r'\d', text))


def check_song_match(user_input: str, song_title: str, mc_title: Optional[str] = None) -> bool:
    user_raw = user_input.strip()
    if not user_raw:
        return False

    # 构建有效候选答案（过滤空字符串和纯空白）
    candidates = []
    for title in (song_title, mc_title):
        if title and title.strip():
            candidates.append(title)

    if not candidates:
        return False

    user_norm = _normalize(user_raw)
    if not user_norm:
        return False

    # 1️⃣ 精确包含（要求用户输入长度≥3，避免单个字母或数字误匹配）
    if len(user_norm) >= 3:
        for cand in candidates:
            cand_norm = _normalize(cand)
            if not cand_norm:
                continue
            if cand_norm in user_norm or user_norm in cand_norm:
                return True

    # 2️⃣ 汉字严格匹配
    user_han = _extract_han(user_norm)
    if user_han:
        for cand in candidates:
            cand_han = _extract_han(_normalize(cand))
            if cand_han and user_han == cand_han:
                return True

    # 3️⃣ 数字严格匹配
    user_digits = _extract_digits(user_norm)
    if user_digits:
        for cand in candidates:
            cand_digits = _extract_digits(_normalize(cand))
            if cand_digits and user_digits == cand_digits:
                return True

    # 4️⃣ 模糊匹配（高阈值，仅输入长度≥5启用）
    if len(user_norm) >= 5:
        for cand in candidates:
            cand_norm = _normalize(cand)
            if not cand_norm or len(cand_norm) < 3:
                continue
            score = max(
                fuzz.partial_ratio(user_norm, cand_norm),
                fuzz.WRatio(user_norm, cand_norm)
            ) / 100.0
            if score >= 0.88:
                return True

    return False
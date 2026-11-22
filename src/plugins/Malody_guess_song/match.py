import re
from rapidfuzz.fuzz import partial_ratio, WRatio
import zhconv
from unidecode import unidecode

_FH = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)

_KC = {
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
    'ガ': '力', 'ギ': '丰', 'グ': '久', 'ゲ': '个', 'ゴ': '己',
    'ザ': '艹', 'ジ': '氵', 'ズ': '又', 'ゼ': '世', 'ゾ': '冫',
    'ダ': '夕', 'ヂ': '千', 'ヅ': '川', 'デ': '天', 'ド': '卜',
    'バ': '八', 'ビ': '匕', 'ブ': '乛', 'ベ': '乀', 'ボ': '术',
    'パ': '八', 'ピ': '匕', 'プ': '乛', 'ペ': '乀', 'ポ': '术',
    'ァ': '了', 'ィ': '亻', 'ゥ': '宀', 'ェ': '工', 'ォ': '才',
    'ッ': '川', 'ャ': '也', 'ュ': '由', 'ョ': '彐',
    'ー': '一',
}

def _remove_brackets_smart(s):
    """智能去除括号：先尝试删除括号及内容；若结果为空，则只删除括号符号"""
    temp = s
    temp = re.sub(r'[（(].*?[）)]', '', temp)
    temp = re.sub(r'[【「『].*?[】」』]', '', temp)
    temp = re.sub(r'[\[].*?[\]]', '', temp)
    temp = re.sub(r'[\{].*?[\}]', '', temp)
    if not temp.strip():
        # 删除后变空，说明整个字符串基本都在括号里，改为只删除括号符号
        s = re.sub(r'[（(）)【「『】」』\[\]{}]', '', s)
        return s
    else:
        return temp

def _nm(t):
    """标准化：全角转半角，转 ASCII，片假名映射，去括号内容，去特殊符号，合并空格，小写"""
    t = t.translate(_FH)
    t = unidecode(t)
    t = ''.join(_KC.get(c, c) for c in t)
    t = _remove_brackets_smart(t)
    t = re.sub(r'[^\w\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u309f\u30a0-\u30ff ]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t.lower()

def _nm_keep_cjk(t):
    """与 _nm 相同，但跳过 unidecode，保留中日韩字符（用于汉字提取）"""
    t = t.translate(_FH)
    t = ''.join(_KC.get(c, c) for c in t)
    t = _remove_brackets_smart(t)
    t = re.sub(r'[^\w\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u309f\u30a0-\u30ff ]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t.lower()

def _eh(t):
    """提取中文并转简体"""
    p = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]')
    hs = p.findall(t)
    return '' if not hs else zhconv.convert(''.join(hs), 'zh-cn')

def _ed(t):
    """提取数字"""
    return ''.join(re.findall(r'\d', t))

def _abbr(s):
    """生成首字母缩写：纯英文数字空格字符串，取每个单词首字母，至少 2 个字母才有效"""
    if not re.fullmatch(r'[a-z0-9 ]+', s):
        return None
    words = s.split()
    abbr = ''.join(w[0] for w in words if w)
    return abbr if len(abbr) >= 2 else None

def check_song_match(user_input, song_title, mc_title=None):
    u = user_input.strip()
    if not u:
        return False

    cs = []
    for t in (song_title, mc_title):
        if t and t.strip():
            cs.append(t)
    if not cs:
        return False

    un = _nm(u)
    un_chinese = _nm_keep_cjk(u)
    if not un:
        return False

    uh = _eh(un_chinese)
    ud = _ed(un)
    u_abbr = _abbr(un)

    for c in cs:
        cn = _nm(c)
        cn_chinese = _nm_keep_cjk(c)
        if not cn:
            continue

        # ------ 新增：短标题全匹配 ------
        if len(cn) < 4 and un == cn:
            return True
        # -----------------------------

        # 1. 汉字匹配
        ch = _eh(cn_chinese)
        if uh and ch and len(set(uh) & set(ch)) >= 2:
            return True

        # 2. 完全匹配的数字
        cd = _ed(cn)
        if ud and cd and ud == cd:
            return True

        # 3. 首字母缩写匹配
        c_abbr = _abbr(cn)
        if u_abbr and c_abbr and u_abbr == c_abbr:
            return True

        # 4. 子串包含匹配（仍要求长度 >= 4）
        if len(un) >= 4 and len(cn) >= 4:
            if cn in un or un in cn:
                return True

        # 5. 模糊匹配（仍要求长度 >= 4）
        if len(un) >= 4 and len(cn) >= 4:
            sc = max(partial_ratio(un, cn), WRatio(un, cn)) / 100.0
            if sc >= 0.96:
                return True

    return False
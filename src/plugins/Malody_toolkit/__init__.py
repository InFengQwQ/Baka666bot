"""
Malody_toolkit - Malody 相关工具插件集

子模块说明：
- acc: 单曲 ACC 计算工具 (/calacc)
- ma2om: Malody 谱面转 osu!mania (/ma2om、/ma2osu、/mc2osu、/mc2om)
- om2ma: osu!mania 谱面转 Malody (/om2ma、/osu2ma、/om2mc、/osu2mc)
- toinverse: 给 .mc/.mcz 谱面补全反键尾判定 (/toinverse)
- toNk: osu!/Malody 谱面转换到任意 K，支持 lambda、局部间隔缩放、全局长条 mapper 和忽略长条冻结 (/to8k、/to8k 0.5、/to8k 0.5 0.5 -g -i)
- malody_download: Malody 谱面下载 (/download)
- malody_rank: Malody 排行榜查询 (/rank)
- malody_rank_draw: 排行榜绘图
- malody_search_chart: 谱面搜索 (/sm)
- malody_top100: TOP100 查询 (/exptop, /mmtop)
- mrv2mr: .mrv → .mr 转换核心库
- mrv2mr_cmd: .mrv → .mr 指令 (/mrv2mr)
- mcz_speed: .osu/.osz/.mc/.mcz 倍速与变调，支持 bid/cid/sid/谱面链接 (/倍速)
- timeinverse: 倒放音频并反转 osu!mania/Malody 谱面时间轴 (/timeinverse)
- replayrd: 回放渲染指令 (/replayrd)
- LevelPredict: 回复 .mc 文件预测难度 (/level)
"""

from nonebot.log import logger

import importlib

# 按顺序导入子模块（每个内含 on_command 注册，模块级代码在此执行）
# 使用 try/except 避免单个子模块失败导致整个插件无法加载
_submodules = [
    "acc",
    "ma2om",
    "malody_hepu",
    "malody_download",
    "malody_rank",
    "malody_rank_draw",
    "malody_search_chart",
    "malody_top100",
    "mrv2mr_cmd",
    "mcz_speed",
    "timeinverse",
    "replayrd",
    "om2ma",
    "LevelPredict.level",
    "tojack_plugin"
]

__baka_import_failures__ = []
for _name in _submodules:
    try:
        importlib.import_module(f".{_name}", package=__package__)
        logger.debug(f"[Malody_toolkit] 已加载子模块: {_name}")
    except Exception as e:
        __baka_import_failures__.append(_name)
        logger.warning(f"[Malody_toolkit] 加载子模块 {_name} 失败: {e}")

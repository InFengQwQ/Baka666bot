import heapq
import math

from nonebot import logger
"""
Malody 分数范围计算器（精确理论值）
=====================================
根据 Malody 游戏的分数计算规则，给定各判定数量，计算理论最小和最大原始分数（1.0x难度）。

函数签名与返回值匹配参考代码。

序列符号: B=BEST, C=COOL, G=GOOD, M=MISS, L=LNMISS
"""

import os
import datetime
from src.storage import plugin_data

HISTORY_FILE = str(plugin_data("MalodyVClientPlugin") / "score_history.txt")


# ==================== 辅助函数 ====================

def _group_best_score_x100(sizes):
    """BEST分组得分x100：每组从combo=0连续执行。"""
    total = 0
    for s in sizes:
        if s > 0:
            total += 100000 * s + 500 * s * (s + 1)
    return total


def _simulate(seq, start_combo=100):
    """模拟序列，返回 (score_float, final_combo)。"""
    bm = {'B': 1000, 'C': 750, 'G': 400, 'M': 0, 'L': 0}
    dm = {'B': 1, 'C': -2, 'G': -8, 'M': -32, 'L': -32}
    combo = start_combo
    total = 0
    for ch in seq:
        base = bm.get(ch, 0)
        delta = dm.get(ch, 0)
        combo = max(0, min(100, combo + delta))
        total += base * (100 + combo)
    return total / 100.0, combo


def _save(best, cool, good, miss, lnmiss, min_val, min_seq, max_val, max_seq):
    """追加记录到历史文件。"""
    if not min_seq and not max_seq:
        return
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(HISTORY_FILE, 'a', encoding='utf-8') as f:
        f.write(f"[{ts}]\n")
        f.write(f"  Input: BEST={best}, COOL={cool}, GOOD={good}, MISS={miss}, LNMISS={lnmiss}\n")
        f.write(f"  Min Score: {min_val:.2f}\n")
        f.write(f"  Min Seq:   {min_seq}\n")
        f.write(f"  Max Score: {max_val:.2f}\n")
        f.write(f"  Max Seq:   {max_seq}\n")
        f.write("\n")


# ==================== 内部计算（返回分数+序列） ====================

def _compute_min(best, cool, good, miss, lnmiss):
    """返回 (score_float, seq_string)"""
    M, L, G, C, B = miss, lnmiss, good, cool, best
    best_x100 = None
    best_seq = ""

    for d in range(M + L + 1):
        ca = max(0, 100 - 32 * d)
        mg = min(G, (ca + 7) // 8) if ca > 0 else 0
        for gd in range(mg + 1):
            cg = max(0, ca - 8 * gd)
            mc = min(C, (cg + 1) // 2) if cg > 0 else 0
            for cd in range(mc + 1):
                cc = max(0, cg - 2 * cd)

                desc = 0
                c = ca
                for _ in range(gd):
                    c = max(0, c - 8)
                    desc += 400 * (100 + c)
                for _ in range(cd):
                    c = max(0, c - 2)
                    desc += 750 * (100 + c)

                seq = []
                seq.append('M' * min(d, M))
                seq.append('L' * max(0, d - M))
                seq.append('G' * gd)
                seq.append('C' * cd)

                rG = G - gd
                rC = C - cd
                rB = B
                rM = M - min(d, M)
                rL = L - max(0, d - M)

                if cc > 0:
                    cur = cc
                    total = desc
                    for _ in range(rG):
                        cur = max(0, cur - 8)
                        total += 400 * (100 + cur)
                        seq.append('G')
                    for _ in range(rC):
                        cur = max(0, cur - 2)
                        total += 750 * (100 + cur)
                        seq.append('C')
                    rm, rl = rM, rL
                    for _ in range(rm + rl):
                        cur = max(0, cur - 32)
                        if rm > 0:
                            seq.append('M'); rm -= 1
                        else:
                            seq.append('L'); rl -= 1
                    seq.append('B' * rB)
                    for _ in range(rB):
                        cur = min(100, cur + 1)
                        total += 100000 + 1000 * cur
                else:
                    pool = []
                    for _ in range(rM):
                        pool.append((0, 32, 'M'))
                    for _ in range(rL):
                        pool.append((0, 32, 'L'))
                    for _ in range(rG):
                        pool.append((40000, 8, 'G'))
                    for _ in range(rC):
                        pool.append((75000, 2, 'C'))
                    pool.sort(key=lambda x: x[0])

                    brem = rB
                    groups = []
                    schars = []
                    scost = 0
                    idx = 0
                    while brem > 0 and idx < len(pool):
                        cost, cap, ch = pool[idx]
                        take = min(brem, cap)
                        if take > 0:
                            groups.append(take)
                            schars.append(ch)
                            scost += cost
                            brem -= take
                        idx += 1
                    if brem > 0:
                        groups.append(brem)

                    bcost = _group_best_score_x100(groups)

                    ucost = 0
                    uchars = []
                    while idx < len(pool):
                        ucost += pool[idx][0]
                        uchars.append(pool[idx][2])
                        idx += 1

                    total = desc + scost + bcost + ucost

                    for i in range(len(schars)):
                        seq.append(schars[i] + 'B' * groups[i])
                    if len(groups) > len(schars):
                        seq.append('B' * groups[-1])
                    seq.append(''.join(uchars))

                seq_s = ''.join(seq)
                if best_x100 is None or total < best_x100:
                    best_x100 = total
                    best_seq = seq_s

    return best_x100 / 100.0, best_seq


def _compute_max(best, cool, good, miss, lnmiss):
    """返回 (score_float, seq_string)"""
    B, C, G = best, cool, good
    best_x100 = 0
    best_seq = ""

    for cr in range(C + 1):
        if 2 * cr > B:
            break
        for gr in range(G + 1):
            if 2 * cr + 8 * gr > B:
                break

            cd = C - cr
            gd = G - gr
            rem = B - 2 * cr - 8 * gr

            total = rem * 200000
            total += cr * (148500 + 199000 + 200000)
            total += gr * (76800 + 193000 + 194000 + 195000 +
                           196000 + 197000 + 198000 + 199000 + 200000)

            combo = 100
            for _ in range(cd):
                combo = max(0, combo - 2)
                total += 750 * (100 + combo)
            for _ in range(gd):
                combo = max(0, combo - 8)
                total += 400 * (100 + combo)

            if total > best_x100:
                best_x100 = total
                seq = []
                seq.append('B' * rem)
                seq.append('CBB' * cr)
                seq.append(('G' + 'B' * 8) * gr)
                seq.append('C' * cd)
                seq.append('G' * gd)
                seq.append('M' * miss)
                seq.append('L' * lnmiss)
                best_seq = ''.join(seq)

    return best_x100 / 100.0, best_seq


# ==================== 公开接口 ====================

def min_raw_score(best, cool, good, miss, lnmiss=0):
    """
    精确最小原始总分（穷举下降段策略 + 分隔符分段模型）。
    已在 B+C+G+M+L ≤ 8 范围内通过完全穷举DP验证（0不匹配）。
    返回 float。
    """
    score, seq = _compute_min(best, cool, good, miss, lnmiss)
    chk, _ = _simulate(seq)
    logger.debug(f"[MIN] best={best} cool={cool} good={good} miss={miss} lnmiss={lnmiss}")
    logger.debug(f"      分数={score:.2f}  序列={seq}")
    if abs(chk - score) > 0.01:
        logger.debug(f"      ⚠ 验证不匹配! 模拟={chk:.2f}")
    return score


def max_raw_score(best, cool, good, miss=0, lnmiss=0):
    """
    精确计算最大原始总分（穷举恢复策略）。
    当 best >= 2*cool + 8*good 时严格精确（已穷举DP验证）；不足时有微小低估。
    返回 float。
    """
    score, seq = _compute_max(best, cool, good, miss, lnmiss)
    chk, _ = _simulate(seq)
    logger.debug(f"[MAX] best={best} cool={cool} good={good} miss={miss} lnmiss={lnmiss}")
    logger.debug(f"      分数={score:.2f}  序列={seq}")
    if abs(chk - score) > 0.01:
        logger.debug(f"      ⚠ 验证不匹配! 模拟={chk:.2f}")
    return score


def calculate_score_range(best, cool, good, miss, lnmiss=0):
    """
    计算理论最小和最大原始分数（1.0x难度），打印极值序列，并追加到历史文件。
    返回 (min_score, max_score) 均为 float。
    """
    mins, minseq = _compute_min(best, cool, good, miss, lnmiss)
    maxs, maxseq = _compute_max(best, cool, good, miss, lnmiss)

    ck1, _ = _simulate(minseq)
    ck2, _ = _simulate(maxseq)

    base = best * 1000 + cool * 750 + good * 400
    ok = base <= mins + 0.01 and maxs <= 2 * base + 0.01

    logger.debug(f"[MIN] best={best} cool={cool} good={good} miss={miss} lnmiss={lnmiss}")
    logger.debug(f"      分数={mins:.2f}  序列={minseq}")
    if abs(ck1 - mins) > 0.01:
        logger.debug(f"      ⚠ 验证不匹配! 模拟={ck1:.2f}")

    logger.debug(f"[MAX] best={best} cool={cool} good={good} miss={miss} lnmiss={lnmiss}")
    logger.debug(f"      分数={maxs:.2f}  序列={maxseq}")
    if abs(ck2 - maxs) > 0.01:
        logger.debug(f"      ⚠ 验证不匹配! 模拟={ck2:.2f}")

    logger.debug(f"[SUM] 底分={base}  最小={mins:.2f}  最大={maxs:.2f}  范围OK={ok}")
    logger.debug()

    _save(best, cool, good, miss, lnmiss, mins, minseq, maxs, maxseq)
    return mins, maxs
# ==================== 核心算法 ====================

def get_L(level: int) -> float:
    if level <= 1:
        return 1.0
    seg1 = max(0, min(level - 1, 9))
    seg2 = max(0, min(level - 10, 5))
    seg3 = max(0, min(level - 15, 5))
    seg4 = max(0, level - 20)
    return (1.05 ** seg1) * (1.04 ** seg2) * (1.03 ** seg3) * (1.02 ** seg4)


def simulate_sequence(order: list, base: dict, delta: dict) -> float:
    combo = 1.0
    total = 0.0
    for t in order:
        combo += delta[t]
        if combo > 1.0: combo = 1.0
        elif combo < 0.0: combo = 0.0
        total += base[t] * (1.0 + combo)
    return total


def mm_range(best: int, cool: int, good: int, miss: int,
             level: int, ratio: float, lnmiss: int = 0):
    N = best + cool + good + miss
    if N == 0:
        return (0.0, 0.0), (0.0, 0.0), 0.0, (0.0, 0.0)
    acc = (best * 1.0 + cool * 0.75 + good * 0.4) / N
    if acc == 1.0:
        A = 0.05
    elif acc > 0.996:
        A = (acc - 0.996) * 10.0
    else:
        A = 0.0
    L = get_L(level)
    raw_max = max_raw_score(best, cool, good, miss, lnmiss)
    raw_min = min_raw_score(best, cool, good, miss, lnmiss)
    score_max = raw_max * ratio
    score_min = raw_min * ratio
    S_max = score_max / (2400.0 * N)
    S_min = score_min / (2400.0 * N)

    def calc_mm(S: float) -> float:
        val = (S + A) * L - 1.0
        return 0.0 if val <= 0.0 else val * 60.0

    mm_max = calc_mm(S_max)
    mm_min = calc_mm(S_min)
    if mm_min > mm_max:
        mm_min, mm_max = mm_max, mm_min
    if S_min > S_max:
        S_min, S_max = S_max, S_min
    return (mm_min, mm_max), (S_min * 100.0, S_max * 100.0), acc, (score_min, score_max)


def mm_exact(best: int, cool: int, good: int, miss: int,
             level: int, ratio: float, score: float):
    N = best + cool + good + miss
    if N == 0:
        return 0.0, 0.0
    acc = (best * 1.0 + cool * 0.75 + good * 0.4) / N
    if acc == 1.0:
        A = 0.05
    elif acc > 0.996:
        A = (acc - 0.996) * 10.0
    else:
        A = 0.0
    L = get_L(level)
    S = score / (2400.0 * N)
    mm = max(0.0, ((S + A) * L - 1.0) * 60.0)
    return mm, S * 100.0


# ==================== 输入校验 ====================
MAX_NOTES = 100_000
MAX_LEVEL = 65536

def validate_input(best: int, cool: int, good: int, miss: int,
                   level: int, ratio: float, lnmiss: int = 0, score: float = None):
    if any(v < 0 for v in (best, cool, good, miss, level, lnmiss)):
        raise ValueError("判定数和等级不能为负数")
    total_notes = best + cool + good + miss   # LNmiss 不计入总物量
    if total_notes == 0:
        raise ValueError("至少需要 1 个音符")
    if total_notes > MAX_NOTES:
        raise ValueError(f"音符总数不能超过 {MAX_NOTES}")
    if level > MAX_LEVEL:
        raise ValueError(f"等级不能超过 {MAX_LEVEL}")
    if not math.isfinite(ratio) or ratio <= 0:
        raise ValueError("ratio 必须为大于0的有限数值")
    if score is not None:
        if not math.isfinite(score) or score < 0:
            raise ValueError("score 必须为非负有限数值")


# ==================== 对外接口 ====================
def process_mm(text: str) -> str:
    """
    处理 /mm 命令文本，返回格式化回复。
    支持可选参数 lnmiss (断面 LNmiss 数量)。
    格式:
      - 旧格式(6参数): best cool good miss level ratio
      - 旧格式(7参数): best cool good miss level ratio score
      - 新格式(7参数): best cool good miss level ratio lnmiss
      - 新格式(8参数): best cool good miss level ratio lnmiss score
    非法输入统一返回全0结果。
    """
    try:
        text = text.strip()
        if not text:
            raise ValueError("参数为空")

        parts = text.split()
        if len(parts) not in (7, 8):
            raise ValueError("参数个数错误，应为 7 或 8 个")

        # 解析公共部分
        best   = int(parts[0])
        cool   = int(parts[1])
        good   = int(parts[2])
        miss   = int(parts[3])
        lnmiss = int(parts[4])
        level  = int(parts[5])
        ratio  = float(parts[6])

        # 根据参数个数决定 score
        if len(parts) == 7:
            score = None
        else:  # len(parts) == 8
            score = float(parts[7])

        validate_input(best, cool, good, miss, level, ratio, lnmiss, score)

        # 计算范围
        (mm_min, mm_max), (S_min, S_max), acc, (score_min, score_max) = \
            mm_range(best, cool, good, miss, level, ratio, lnmiss)

        if score is None:
            reply = (
                f"acc : {100*acc:.4f}\n"
                f"分数范围 : {score_min:.0f} - {score_max:.0f}\n"
                f"MM 范围: {mm_min:.4f} ~ {mm_max:.4f}\n"
                f"完成度范围: {S_min:.2f}% ~ {S_max:.2f}%"
            )
            return reply
        else:
            mm, S = mm_exact(best, cool, good, miss, level, ratio, score)
            # 幸运值
            if mm_max > mm_min:
                luck = (mm - mm_min) / (mm_max - mm_min) * 100.0
                luck = max(0.0, min(100.0, luck))
            else:
                luck = 100.0 if mm >= mm_max else 0.0
            # 潜力 MM = 幸运值(小数) * 剩余空间
            potential = (1.0 - luck / 100.0) * (mm_max - mm) if mm_max > mm else 0.0
            reply = (
                f"acc : {100*acc:.4f}\n"
                f"分数范围 : {score_min:.0f} - {score_max:.0f}\n"
                f"MM 范围: {mm_min:.4f} - {mm_max:.4f}\n"
                f"完成度范围: {S_min:.2f}% - {S_max:.2f}%\n"
                f"当前 MM: {mm:.4f}  完成度: {S:.2f}%\n"
                f"稳定率: {luck:.0f}%  潜力 MM: {potential:.4f}"
            )
            return reply

    except Exception:
        # 统一返回全0
        return "MM 范围: 0.0000 ~ 0.0000\n完成度范围: 0.00% ~ 0.00%\n当前 MM: 0.0000  完成度: 0.00%\n稳定值: 0%  潜力 MM: 0.0000"

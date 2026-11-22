#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tojack.py — 将 .mc 谱面中所有 beat/endbeat 的分母统一为指定值（默认 4）。

用法:
    python tojack.py 输入文件.mc [k]

说明:
    - 默认 k=4
    - 若 k<=0 视为非法参数
    - 输入若为 .mc（JSON 谱面），处理 note 数组中的 beat 与 endbeat
    - 输出文件命名: 原文件名.tojack{k}.mc
"""

import json
import os
import sys


def convert_beat(beat, k):
    """把 beat = [a, b, c] 的 b/c 四舍五入到以 k 为分母的最近位置。"""
    if not isinstance(beat, list) or len(beat) < 3:
        return beat
    a, b, c = beat[0], beat[1], beat[2]
    if c == k:
        return beat
    # round(b * k / c)，使用整数运算避免浮点误差
    new_b = (2 * b * k + c) // (2 * c)
    a += new_b // k
    new_b %= k
    new_beat = [a, new_b, k]
    if len(beat) > 3:
        new_beat.extend(beat[3:])
    return new_beat


def main():
    if len(sys.argv) < 2:
        print("用法: python tojack.py 输入文件.mc [k]", file=sys.stderr)
        return 1

    input_path = sys.argv[1]
    k = 4
    if len(sys.argv) >= 3:
        try:
            k = int(sys.argv[2])
        except ValueError:
            print(f"k 必须是正整数，收到: {sys.argv[2]}", file=sys.stderr)
            return 1
    if k <= 0:
        print(f"k 必须是正整数，收到: {k}", file=sys.stderr)
        return 1

    with open(input_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"不是有效的 JSON 谱面文件: {e}", file=sys.stderr)
            return 1

    notes = data.get("note")
    if not isinstance(notes, list):
        print("note 字段缺失或格式错误", file=sys.stderr)
        return 1

    for note in notes:
        if not isinstance(note, dict):
            continue
        if "beat" in note:
            note["beat"] = convert_beat(note["beat"], k)
        if "endbeat" in note:
            note["endbeat"] = convert_beat(note["endbeat"], k)

    base, ext = os.path.splitext(input_path)
    if ext.lower() != ".mc":
        base = input_path
    output_path = f"{base}.tojack{k}.mc"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    print(f"已生成: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
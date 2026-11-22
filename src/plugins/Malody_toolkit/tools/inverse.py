import sys
import json
from fractions import Fraction
from collections import defaultdict

def beat_to_fraction(beat):
    """将 [整数, 分子, 分母] 转为 Fraction"""
    return Fraction(beat[0] * beat[2] + beat[1], beat[2])

def fraction_to_beat(frac):
    """将 Fraction 转回 [整数, 分子, 分母]"""
    integer = frac.numerator // frac.denominator
    remainder = frac.numerator % frac.denominator
    return [integer, remainder, frac.denominator]

def process_mc(input_path, n=None, m=None):
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # type=1 才是音频标记。普通音符也可能带有 sound 字段，不能按
    # sound 字段过滤，否则会把整张谱面误删为空谱面。
    all_notes = data.get('note', [])
    notes = [
        note for note in all_notes
        if not (isinstance(note, dict) and str(note.get('type', '0')) == '1')
    ]

    # 按 column 分组
    col_map = defaultdict(list)
    for note in notes:
        if not isinstance(note, dict):
            continue
        if 'column' not in note or 'beat' not in note:
            continue
        col_map[note['column']].append(note)

    # 确定是否使用固定 delta
    fixed_delta = None
    if n is not None and m is not None:
        fixed_delta = Fraction(n, m)

    for col, items in col_map.items():
        # 按拍子排序
        items.sort(key=lambda note: beat_to_fraction(note['beat']))
        for i, note in enumerate(items):
            if i < len(items) - 1:
                # 不是最后一个：下个 note 的拍子 - delta
                next_beat = items[i + 1]['beat']
                if fixed_delta is not None:
                    delta = fixed_delta
                else:
                    # 使用当前 note 拍子的分母：1 / beat[2]
                    delta = Fraction(1, note['beat'][2])
                end_frac = beat_to_fraction(next_beat) - delta
            else:
                # 最后一个：当前拍子 + 1 完整拍
                end_frac = beat_to_fraction(note['beat']) + Fraction(1, 1)
            note['endbeat'] = fraction_to_beat(end_frac)

    # 保留音频标记和其他合法 note，只更新普通音符的 endbeat。
    data['note'] = all_notes

    # 生成输出文件名
    if input_path.lower().endswith('.mc'):
        output_path = input_path[:-3] + '_inverse.mc'
    else:
        output_path = input_path + '_inverse.mc'

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f'Inverse 版本已保存至: {output_path}')

if __name__ == '__main__':
    if len(sys.argv) == 2:
        # 不指定 n,m，使用默认行为
        input_file = sys.argv[1]
        n, m = None, None
    elif len(sys.argv) == 4:
        input_file = sys.argv[1]
        try:
            n = int(sys.argv[2])
            m = int(sys.argv[3])
            if m == 0:
                raise ValueError
        except ValueError:
            print('n 和 m 必须是整数，且 m 不能为 0')
            sys.exit(1)
    else:
        print('用法:')
        print('  指定 n,m: python inverse.py <输入.mc> <n> <m>')
        print('  自适应:   python inverse.py <输入.mc>')
        print('示例: python inverse.py chart.mc 1 4')
        sys.exit(1)

    process_mc(input_file, n, m)

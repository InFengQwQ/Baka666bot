"""
mrv → mr 转换工具（版本 4.3.7，rank 自动取自 score_data[4]）
用法：python mrv2mr.py 文件.mrv [手动rank]
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import blackboxprotobuf
try:
    from . import replay_pb2   # 作为包加载时
except ImportError:
    import replay_pb2          # 作为脚本直接运行时


# ==================== 辅助函数 ====================

def _decode_mrv_to_dict(file_path: str) -> dict:
    with open(file_path, 'rb') as f:
        data = f.read()
    msg, _ = blackboxprotobuf.decode_message(data)

    def convert_bytes(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                obj[k] = convert_bytes(v)
            return obj
        elif isinstance(obj, list):
            return [convert_bytes(i) for i in obj]
        elif isinstance(obj, bytes):
            try:
                return obj.decode('utf-8')
            except UnicodeDecodeError:
                return obj.hex()
        return obj
    return convert_bytes(msg)


class MrvReplay:
    """
    解析 .mrv 文件，提取 .mr 所需的所有字段。
    """
    def __init__(self, file_path: str, force_rank=None):
        self.file_path = str(file_path)
        self.status = "init"
        self.error_message = ""

        # 1. 尝试用 protobuf 解析（获取动作列表）
        try:
            with open(file_path, 'rb') as f:
                raw_bytes = f.read()
            replay_pb = replay_pb2.ReplayFile()
            replay_pb.ParseFromString(raw_bytes)
        except Exception as e:
            self.status = "ParseError"
            self.error_message = f"Protobuf解析失败: 请反馈bot主人"
            self.actions = []
            return

        # 2. 黑盒解析所有字段（获取头部信息）
        self.raw_data = _decode_mrv_to_dict(file_path)
        header = self.raw_data

        # 歌曲信息
        self.song_title = header.get("1", "")
        self.song_artist = header.get("2", "")
        self.difficulty_name = header.get("4", "")
        self.beatmap_md5 = header.get("5", "")
        # player_name 不写入 mr 二进制

        # 分数与判定
        score_data = header.get("8", {})
        self.score = score_data.get("5", 0)
        self.max_combo = score_data.get("6", 0)
        self.best_count = score_data.get("7", 0)
        self.cool_count = score_data.get("8", 0)
        self.good_count = score_data.get("9", 0)
        self.miss_count = score_data.get("10", 0)
        self.unknown_count = 0
        self.mods_flags = 0

        # 字母等级 (rank) : 优先手动，否则自动从字段 "4" 提取
        if force_rank is not None:
            self.rank = force_rank
            print(f"[配置] 使用手动指定的 rank = {self.rank}")
        else:
            self.rank = score_data.get("4", 0)
            print(f"[自动] 从 score_data['4'] 提取 rank = {self.rank}")

        # 时间戳
        self.timestamp = header.get("12", 0)

        # 动作列表（protobuf 解析）
        try:
            self.actions = self._parse_records_from_pb(replay_pb.records)
            if not self.actions:
                self.status = "NoValidActions"
                self.error_message = "没有有效动作"
            else:
                self.status = "OK"
        except Exception as e:
            self.status = "ParseError"
            self.error_message = str(e)
            self.actions = []

    def _parse_records_from_pb(self, records_pb) -> list[tuple[int, int, int]]:
        actions = []
        for rec in records_pb:
            time_ms = rec.time
            for cell in rec.cells:
                field = cell.WhichOneof('cell_oneof')
                if field == 'input_indexed_down':
                    col = cell.input_indexed_down
                    if 0 <= col < 18:
                        actions.append((time_ms, 1, col))
                elif field == 'input_indexed_up':
                    col = cell.input_indexed_up
                    if 0 <= col < 18:
                        actions.append((time_ms, 2, col))
        actions.sort(key=lambda x: x[0])
        return actions


# ==================== .mr 写入 ====================

def _write_prefixed_string(f, s: str) -> None:
    data = s.encode("utf-8")
    f.write(struct.pack("<i", len(data)))
    f.write(data)


def convert_mrv_to_mr(mrv_path: str, mr_path: str, force_rank=None) -> bool:
    print(f"解析 .mrv: {mrv_path}")
    mrv = MrvReplay(mrv_path, force_rank=force_rank)
    if mrv.status != "OK":
        print(f"错误：无法解析 mrv，状态={mrv.status}，信息={mrv.error_message}")
        return False

    # 打印关键信息用于核对
    print(f"  mrv 歌曲标题  : {mrv.song_title}")
    print(f"  mrv 艺术家    : {mrv.song_artist}")
    print(f"  mrv 难度名    : {mrv.difficulty_name}")
    print(f"  mrv MD5       : {mrv.beatmap_md5}")
    print(f"  mrv score     : {mrv.score}")
    print(f"  mrv combo     : {mrv.max_combo}")
    print(f"  mrv 判定      : best={mrv.best_count} cool={mrv.cool_count} good={mrv.good_count} miss={mrv.miss_count}")
    print(f"  mrv 字母等级  : {mrv.rank} (0-4: A-E, 10-14: ProA-ProE)")
    print(f"  mrv timestamp : {mrv.timestamp}")
    print(f"  mrv 动作数量  : {len(mrv.actions)}")

    # 写入 .mr 二进制
    with open(mr_path, "wb") as f:
        # 文件头
        _write_prefixed_string(f, "mr format head")
        f.write(struct.pack("<BBBB", 7, 3, 4, 0))   # patch, minor, major, reserved → 版本 4.3.7

        # 歌曲信息
        _write_prefixed_string(f, mrv.beatmap_md5)
        _write_prefixed_string(f, mrv.difficulty_name)
        _write_prefixed_string(f, mrv.song_title)
        _write_prefixed_string(f, mrv.song_artist)

        # 统计
        f.write(struct.pack("<i", mrv.score))
        f.write(struct.pack("<i", mrv.max_combo))
        f.write(struct.pack("<i", mrv.best_count))
        f.write(struct.pack("<i", mrv.cool_count))
        f.write(struct.pack("<i", mrv.good_count))
        f.write(struct.pack("<i", mrv.miss_count))
        f.write(struct.pack("<i", mrv.unknown_count))
        f.write(struct.pack("<i", mrv.mods_flags))
        f.write(struct.pack("<i", mrv.rank))       # 字母等级

        # 数据段标识
        _write_prefixed_string(f, "mr data")
        f.write(struct.pack("<i", 0))               # reserved2
        f.write(struct.pack("<i", len(mrv.actions)))
        f.write(struct.pack("<B", 0))               # flag_byte
        f.write(struct.pack("<i", mrv.timestamp))
        f.write(struct.pack("<i", 0))               # reserved3

        # 动作
        for time_ms, action, col in mrv.actions:
            f.write(struct.pack("<iBB", time_ms, action, col))

    print(f"✅ 转换成功: {mr_path}")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python mrv2mr.py 文件.mrv [手动rank]")
        print("  手动rank 可选，例如 2 表示 C 判定")
        sys.exit(1)

    in_path = sys.argv[1]
    force = int(sys.argv[2]) if len(sys.argv) > 2 else None

    if not in_path.lower().endswith(".mrv"):
        print("错误：输入文件扩展名必须为 .mrv")
        sys.exit(1)

    out_path = Path(in_path).with_suffix(".mr")
    success = convert_mrv_to_mr(in_path, str(out_path), force_rank=force)
    if not success:
        sys.exit(1)
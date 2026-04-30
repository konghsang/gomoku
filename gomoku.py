"""
五子棋 (Gomoku) - 双人对战 & 远程联机

功能：
- 本地双人对战
- 远程 TCP/IP 联机对战
- 黑方禁手规则（三三、四四、长连）
- 对局记录保存 (JSON)
- 落子音效
"""

import ctypes
import json
import math
import os
import queue
import random
import socket
import struct
import sys
import threading
import time
import tkinter as tk
import wave
from datetime import datetime
from enum import IntEnum
from tkinter import filedialog, messagebox
from dataclasses import dataclass

try:
    import winsound
except ImportError:
    winsound = None

BOARD_SIZE = 15
CELL_SIZE = 38
MARGIN = 28
STONE_RADIUS = 15

PROTOCOL_VERSION = 1
HEARTBEAT_INTERVAL = 5.0
HEARTBEAT_TIMEOUT = 15.0


class Stone(IntEnum):
    EMPTY = 0
    BLACK = 1
    WHITE = 2


@dataclass
class MoveCheckResult:
    legal: bool
    message: str
    win: bool = False


def inside(x: int, y: int) -> bool:
    """检查坐标是否在棋盘边界内。"""
    return 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE


def count_in_direction(board: list[list[int]], x: int, y: int, dx: int, dy: int, color: int) -> int:
    """计算从 (x, y) 出发在 (dx, dy) 方向上连续同色棋子的数量（包含自身）。"""
    total = 1

    nx, ny = x + dx, y + dy
    while inside(nx, ny) and board[ny][nx] == color:
        total += 1
        nx += dx
        ny += dy

    nx, ny = x - dx, y - dy
    while inside(nx, ny) and board[ny][nx] == color:
        total += 1
        nx -= dx
        ny -= dy

    return total


def line_has_exact_five(board: list[list[int]], x: int, y: int, color: int) -> bool:
    """检查落子后是否在任意方向上恰好形成 5 连。"""
    for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
        if count_in_direction(board, x, y, dx, dy, color) == 5:
            return True
    return False


def line_has_five_or_more(board: list[list[int]], x: int, y: int, color: int) -> bool:
    """检查落子后是否在任意方向上形成 5 连或以上。"""
    for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
        if count_in_direction(board, x, y, dx, dy, color) >= 5:
            return True
    return False


def line_has_overline(board: list[list[int]], x: int, y: int, color: int) -> bool:
    """检查落子后是否在任意方向上形成 6 连或以上（长连接手）。"""
    for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
        if count_in_direction(board, x, y, dx, dy, color) >= 6:
            return True
    return False


def _point_on_segment(px: int, py: int, sx: int, sy: int, dx: int, dy: int, length: int) -> bool:
    """检查 (px, py) 是否在以 (sx, sy) 为起点的长度为 length 的 (dx, dy) 方向线段上。

    对于水平线段 (dy==0)，只沿 x 方向延伸，所以 py 必须等于 sy。
    对于垂直线段 (dx==0)，只沿 y 方向延伸，所以 px 必须等于 sx。
    否则一个不同行/列的落子点会被错误判定为在线段上。
    """
    # 水平线段：y 坐标必须固定不变
    if dy == 0 and py != sy:
        return False
    # 垂直线段：x 坐标必须固定不变
    if dx == 0 and px != sx:
        return False

    if dx != 0:
        if (px - sx) % dx != 0:
            return False
        k = (px - sx) // dx
    else:
        k = (py - sy) // dy

    if dy != 0:
        if (py - sy) % dy != 0:
            return False
        if dx != 0 and (py - sy) // dy != k:
            return False

    return 0 <= k < length


def _build_line_segment(board: list[list[int]], x: int, y: int, dx: int, dy: int):
    """
    沿 (dx, dy) 方向构建经过 (x, y) 的线段（包含已落子的黑子和空位）。
    遇到白子或棋盘边界时停止。
    返回 (values, positions)：
    - values: 从近到远的单元格值列表（不含白子，不含越界），(x,y) 在中间
    - positions: 对应 (nx, ny) 坐标列表
    """
    back_values = []
    back_pos = []
    nx, ny = x - dx, y - dy
    while inside(nx, ny) and board[ny][nx] != Stone.WHITE:
        back_values.append(board[ny][nx])
        back_pos.append((nx, ny))
        nx -= dx
        ny -= dy

    fwd_values = []
    fwd_pos = []
    nx, ny = x + dx, y + dy
    while inside(nx, ny) and board[ny][nx] != Stone.WHITE:
        fwd_values.append(board[ny][nx])
        fwd_pos.append((nx, ny))
        nx += dx
        ny += dy

    back_values.reverse()
    back_pos.reverse()
    values = back_values + [board[y][x]] + fwd_values
    positions = back_pos + [(x, y)] + fwd_pos
    return values, positions


def _count_jump_live_three_in_direction(board: list[list[int]], x: int, y: int, dx: int, dy: int) -> int:
    """
    检测在 (dx, dy) 方向上，(x, y) 落子后是否形成跳活三。
    
    跳活三模式（标记 B=黑子, _=空位, P=落子点）：
    模式1: _ B B _ B _   (落子点为第2个黑子)
    模式2: _ B _ B B _   (落子点为第4个黑子)
    
    即：总共 3 个黑子，其中 1 个间隙，两端开放，
    且至少一端向外还有至少 1 个空位（保证能形成活四）。
    
    返回值：0 或 1（每个方向最多 1 个跳活三模式）。
    """
    values, positions = _build_line_segment(board, x, y, dx, dy)
    
    # 在 positions 中找到 (x, y) 的索引
    try:
        move_idx = positions.index((x, y))
    except ValueError:
        return 0
    
    # 在 values 序列中滑动窗口检测跳活三模式
    # 跳活三中 3 个黑子跨越 5 个格位（黑-黑-空-黑 或 黑-空-黑-黑）
    # 两端还需各有一个空位，所以总窗口至少 7 格
    for win_size in (5, 6, 7):
        for start in range(0, len(values) - win_size + 1):
            if not (start <= move_idx < start + win_size):
                # 窗口必须包含落子点
                continue
            
            window = values[start:start + win_size]
            
            # 统计黑子数量（必须恰好 3 个）
            black_count = sum(1 for v in window if v == Stone.BLACK)
            if black_count != 3:
                continue
            
            # 找到 3 个黑子的索引
            black_indices = [i for i, v in enumerate(window) if v == Stone.BLACK]
            
            # 检查 3 个黑子是否有 1 个间隙（非连续）
            # 即跨度 = 最大索引 - 最小索引 + 1，减去 3 应等于 1
            span = black_indices[-1] - black_indices[0] + 1
            if span != 4:  # 3 黑 + 1 间隙 = 4 格
                continue
            
            # 检查间隙两侧是否确实有黑子（确保不是末端空格）
            # 间隙位置 = 没有黑子的那个索引
            gap_cells = [i for i in range(black_indices[0], black_indices[-1] + 1) if i not in black_indices]
            if len(gap_cells) != 1:
                continue
            
            # 间隙必须是空位（不能是白子——但我们已经过滤了白子）
            if window[gap_cells[0]] != Stone.EMPTY:
                continue
            
            # 检查两端开放（两端紧邻位为空）
            before_idx = black_indices[0] - 1
            after_idx = black_indices[-1] + 1
            
            if before_idx < 0 or after_idx >= len(window):
                # 窗口边界到了棋盘边界或白子，不是开放端
                continue
            
            if window[before_idx] != Stone.EMPTY or window[after_idx] != Stone.EMPTY:
                continue
            
            # 检查至少一端有 2+ 连续空位（活四潜力）
            open2_before = (before_idx - 1 >= 0 and window[before_idx - 1] == Stone.EMPTY)
            open2_after = (after_idx + 1 < len(window) and window[after_idx + 1] == Stone.EMPTY)
            
            if not open2_before and not open2_after:
                continue
            
            # 找到有效的跳活三模式
            return 1
    
    return 0


def _count_jump_four_in_direction(board: list[list[int]], x: int, y: int, dx: int, dy: int) -> int:
    """
    检测在 (dx, dy) 方向上，(x, y) 落子后是否形成跳四。
    
    跳四模式：B B _ B B  （中间 1 个间隙，4 个黑子）
    落子点可以是任意一个黑子位置。
    
    至少一端紧邻空位即为有效的"四"。
    
    返回值：0 或 1。
    """
    values, positions = _build_line_segment(board, x, y, dx, dy)
    
    try:
        move_idx = positions.index((x, y))
    except ValueError:
        return 0
    
    # 跳四模式为：4 个黑子在 5 格范围内，中间有 1 个间隙
    # 两端至少有一端紧邻空位
    for win_size in (5, 6):
        for start in range(0, len(values) - win_size + 1):
            if not (start <= move_idx < start + win_size):
                continue
            
            window = values[start:start + win_size]
            
            black_count = sum(1 for v in window if v == Stone.BLACK)
            if black_count != 4:
                continue
            
            black_indices = [i for i, v in enumerate(window) if v == Stone.BLACK]
            
            # 4 个黑子 + 1 个间隙 = 跨度 5
            span = black_indices[-1] - black_indices[0] + 1
            if span != 5:
                continue
            
            # 间隙位置
            gap_cells = [i for i in range(black_indices[0], black_indices[-1] + 1) if i not in black_indices]
            if len(gap_cells) != 1:
                continue
            
            if window[gap_cells[0]] != Stone.EMPTY:
                continue
            
            # 至少一端紧邻空位（或超出窗口边界时，需检查是否是越界/白子）
            before_idx = black_indices[0] - 1
            after_idx = black_indices[-1] + 1
            
            open_forward = (after_idx < len(window) and window[after_idx] == Stone.EMPTY)
            open_backward = (before_idx >= 0 and window[before_idx] == Stone.EMPTY)
            
            if not open_forward and not open_backward:
                continue
            
            return 1
    
    return 0


def count_black_four_targets(board: list[list[int]], place_x: int, place_y: int) -> int:
    """
    统计棋盘上黑方长度为 4 且经过落子点的连通线段数量（至少一端开放）。

    用于四四禁手检测：仅统计包含当前落子 (place_x, place_y) 的线段，
    满足规则"该落子必须在每一个四中"。
    """
    targets = 0

    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            if board[y][x] != Stone.BLACK:
                continue

            for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
                # 跳过已被前驱黑子覆盖的线段起点
                prev_x, prev_y = x - dx, y - dy
                if inside(prev_x, prev_y) and board[prev_y][prev_x] == Stone.BLACK:
                    continue

                length = 0
                nx, ny = x, y
                while inside(nx, ny) and board[ny][nx] == Stone.BLACK:
                    length += 1
                    nx += dx
                    ny += dy

                if length != 4:
                    continue

                # 规则要求：落子必须在每一个四中
                if not _point_on_segment(place_x, place_y, x, y, dx, dy, 4):
                    continue

                forward_open = inside(nx, ny) and board[ny][nx] == Stone.EMPTY
                backward_open = inside(prev_x, prev_y) and board[prev_y][prev_x] == Stone.EMPTY
                if forward_open or backward_open:
                    targets += 1

    # 加上跳四计数
    for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
        targets += _count_jump_four_in_direction(board, place_x, place_y, dx, dy)

    return targets


def count_black_three_targets(board: list[list[int]], place_x: int, place_y: int) -> int:
    """
    统计棋盘上黑方长度为 3 且经过落子点的连通线段数量（两端均开放）。

    用于三三禁手检测：仅统计包含当前落子 (place_x, place_y) 的线段，
    满足规则"该落子必须在每一个活三中"。
    """
    targets = 0

    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            if board[y][x] != Stone.BLACK:
                continue

            for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
                prev_x, prev_y = x - dx, y - dy
                if inside(prev_x, prev_y) and board[prev_y][prev_x] == Stone.BLACK:
                    continue

                length = 0
                nx, ny = x, y
                while inside(nx, ny) and board[ny][nx] == Stone.BLACK:
                    length += 1
                    nx += dx
                    ny += dy

                if length != 3:
                    continue

                # 规则要求：落子必须在每一个活三中
                if not _point_on_segment(place_x, place_y, x, y, dx, dy, 3):
                    continue

                forward_open = inside(nx, ny) and board[ny][nx] == Stone.EMPTY
                backward_open = inside(prev_x, prev_y) and board[prev_y][prev_x] == Stone.EMPTY
                if not (forward_open and backward_open):
                    continue

                # 活三判定：两端紧邻位必须为空，且至少有一端再往外一格也为空
                #（即该侧有连续两个空位，这样落子后才能形成活四）
                forward_open2 = inside(nx + dx, ny + dy) and board[ny + dy][nx + dx] == Stone.EMPTY
                backward_open2 = inside(prev_x - dx, prev_y - dy) and board[prev_y - dy][prev_x - dx] == Stone.EMPTY
                if forward_open2 or backward_open2:
                    targets += 1

    # 加上跳活三计数
    for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
        targets += _count_jump_live_three_in_direction(board, place_x, place_y, dx, dy)

    return targets


def check_black_move(board: list[list[int]], x: int, y: int) -> MoveCheckResult:
    """
    检查黑方落子是否合法（含禁手检测）。

    检测顺序：成五获胜 → 长连接手 → 四四禁手 → 三三禁手。
    规则规定：五连与任何禁手（包括长连、四四、三三）同时形成时，禁手失效，五连获胜。
    """
    if line_has_exact_five(board, x, y, Stone.BLACK):
        return MoveCheckResult(True, "黑方成五，黑方获胜。", True)

    if line_has_overline(board, x, y, Stone.BLACK):
        return MoveCheckResult(False, "黑方长连禁手。")

    four_targets = count_black_four_targets(board, x, y)
    if four_targets >= 2:
        return MoveCheckResult(False, "黑方四四禁手。")

    three_targets = count_black_three_targets(board, x, y)
    if three_targets >= 2:
        return MoveCheckResult(False, "黑方三三禁手。")

    return MoveCheckResult(True, "")


def check_white_move(board: list[list[int]], x: int, y: int) -> MoveCheckResult:
    """检查白方落子是否合法（白方无禁手，仅检测成五）。"""
    if line_has_five_or_more(board, x, y, Stone.WHITE):
        return MoveCheckResult(True, "白方成五，白方获胜。", True)
    return MoveCheckResult(True, "")


class GomokuApp:
    """五子棋应用主类，负责 UI 渲染、游戏逻辑、网络通信和状态管理。"""

    RESET_COOLDOWN = 0.6

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("五子棋 - 双人对战")
        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_dir, 'tu.ico')
        if os.path.exists(icon_path):
            self.root.iconbitmap(icon_path)
        self.root.resizable(False, False)

        self.board = [[Stone.EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.current_player = Stone.BLACK
        self.game_over = False
        self.last_move: tuple[int, int] | None = None
        self.move_records: list[dict[str, object]] = []
        self.game_start_time = datetime.now()

        self.networked = False
        self.mode: str | None = None
        self.is_host = False
        self.remote_black_is_host = True
        self.my_color: int | None = None
        self.peer_color: int | None = None
        self.net_socket: socket.socket | None = None
        self.net_thread: threading.Thread | None = None
        self.net_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._net_lock = threading.Lock()
        self.reset_cooldown = self.RESET_COOLDOWN
        self.last_reset_at = 0.0
        self.protocol_ok = True
        self.session_id = 0
        self.pending_start = False
        self._last_message_time = time.monotonic()
        self._last_message_time_lock = threading.Lock()
        self._heartbeat_id = 0
        self._network_dialog_open = False
        self._network_dialog: tk.Toplevel | None = None

        self._build_ui()
        self._center_window()
        self._redraw()
        self._set_status("请选择模式：本地双人或远程联机。")
        self.root.after(100, self._process_network_queue)

    def _center_window(self) -> None:
        """将窗口在屏幕中央显示。"""
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def _build_ui(self) -> None:
        window_width = MARGIN * 2 + CELL_SIZE * (BOARD_SIZE - 1) + 280
        window_height = max(
            MARGIN * 2 + CELL_SIZE * (BOARD_SIZE - 1) + 90,
            540,  # 确保侧面板内容不被裁剪
        )
        self.root.geometry(f"{window_width}x{window_height}")

        main = tk.Frame(self.root, bg="#d8b36a")
        main.pack(fill=tk.BOTH, expand=True)

        canvas_width = MARGIN * 2 + CELL_SIZE * (BOARD_SIZE - 1)
        canvas_height = canvas_width
        self.canvas = tk.Canvas(main, width=canvas_width, height=canvas_height, bg="#d8b36a", highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, padx=12, pady=12)
        self.canvas.bind("<Button-1>", self._on_click)

        side = tk.Frame(main, width=250, bg="#f5f0e6")
        side.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 12), pady=16)
        side.pack_propagate(False)

        title = tk.Label(side, text="五子棋", font=("Microsoft YaHei", 22, "bold"), bg="#f5f0e6", fg="#2c2c2c")
        title.pack(pady=(18, 8))

        info = "规则说明\n" "1. 黑方先手\n" "2. 黑方禁手：三三、四四、长连\n" "3. 白方按普通五子棋规则\n" "4. 连成 5 子即获胜"
        tk.Label(side, text=info, justify=tk.LEFT, bg="#f5f0e6", fg="#3a3a3a", font=("Microsoft YaHei", 10), wraplength=200).pack(
            padx=18, pady=(4, 14), anchor="w"
        )

        self.status_var = tk.StringVar(value="")
        tk.Label(
            side,
            textvariable=self.status_var,
            justify=tk.LEFT,
            bg="#f5f0e6",
            fg="#8a3b12",
            font=("Microsoft YaHei", 10, "bold"),
            wraplength=200,
        ).pack(padx=18, pady=(0, 14), anchor="w")

        tk.Button(side, text="本地双人", command=self._enter_local_mode, relief=tk.RAISED, bd=2, font=("Microsoft YaHei", 11)).pack(
            padx=18, pady=(10, 8), fill=tk.X
        )

        tk.Button(side, text="远程联机", command=self._enter_remote_mode, relief=tk.RAISED, bd=2, font=("Microsoft YaHei", 11)).pack(
            padx=18, pady=(0, 8), fill=tk.X
        )

        tk.Button(side, text="重新开始", command=self._on_reset_clicked, relief=tk.RAISED, bd=2, font=("Microsoft YaHei", 11)).pack(
            padx=18, pady=(0, 8), fill=tk.X
        )

        tk.Button(side, text="保存对局", command=self._save_record_dialog, relief=tk.RAISED, bd=2, font=("Microsoft YaHei", 11)).pack(
            padx=18, pady=(0, 8), fill=tk.X
        )

        tk.Label(
            side,
            text="提示：点击棋盘落子。\n黑方若触发禁手，会被直接判负。",
            justify=tk.LEFT,
            bg="#f5f0e6",
            fg="#555555",
            font=("Microsoft YaHei", 9),
            wraplength=200,
        ).pack(padx=18, pady=(10, 6), anchor="w")

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _reset_game(self, show_dialog: bool = True) -> None:
        self.board = [[Stone.EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.current_player = Stone.BLACK
        self.game_over = False
        self.last_move = None
        self.move_records = []
        self.game_start_time = datetime.now()
        self._update_cursor()
        self._redraw()
        self._set_status("黑方先手。黑方禁手：三三、四四、长连。")
        if show_dialog:
            self._show_start_dialog()

    def _update_cursor(self) -> None:
        """根据游戏状态更新棋盘光标样式。"""
        if self.game_over or self.mode is None:
            self.canvas.config(cursor="arrow")
        else:
            self.canvas.config(cursor="hand2")

    def _on_reset_clicked(self) -> None:
        if self.mode == "remote" and self.networked:
            now = time.monotonic()
            if now - self.last_reset_at < self.reset_cooldown:
                return
            self.last_reset_at = now
            self.session_id += 1
            self._send_net(f"RESET|{self.session_id}")
            self._reset_game(show_dialog=False)
            self._show_start_dialog()
            return

        self._reset_game()

    def _show_start_dialog(self) -> None:
        messagebox.showinfo("开始对局", "黑方先手。黑方禁手：三三、四四、长连。")

    def _show_result_dialog(self, message: str) -> None:
        messagebox.showinfo("对局结束", message)

    def _play_move_sound(self) -> None:
        try:
            mp3_path = self._find_drop_stone_mp3()
            if mp3_path:
                self._play_mp3(mp3_path)
                return

            sound_path = self._ensure_stone_sound()
            if sound_path and winsound:
                winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return

            if winsound:
                winsound.MessageBeep(winsound.MB_OK)
            else:
                self.root.bell()
        except (OSError, AttributeError):
            self.root.bell()

    def _find_drop_stone_mp3(self) -> str | None:
        """查找落子音效 MP3 文件。"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        mp3_path = os.path.join(base_dir, "luozi.mp3")
        return mp3_path if os.path.exists(mp3_path) else None

    def _play_mp3(self, mp3_path: str) -> None:
        alias = "luozi_sound"
        mci = ctypes.windll.winmm.mciSendStringW
        mci(f"close {alias}", None, 0, None)
        mci(f'open "{mp3_path}" type mpegvideo alias {alias}', None, 0, None)
        mci(f"play {alias} from 0", None, 0, None)

    def _ensure_stone_sound(self) -> str | None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        sound_path = os.path.join(base_dir, "stone.wav")
        if os.path.exists(sound_path):
            return sound_path

        try:
            self._generate_stone_sound(sound_path)
            return sound_path
        except (OSError, wave.Error):
            return None

    def _generate_stone_sound(self, sound_path: str) -> None:
        """生成一个简单的落子音效 WAV 文件（噪声 + 正弦波衰减）。"""
        sample_rate = 44100
        duration = 0.08
        total_samples = int(sample_rate * duration)

        with wave.open(sound_path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)

            for i in range(total_samples):
                t = i / sample_rate
                envelope = math.exp(-28 * t)
                noise = (random.random() * 2 - 1) * 0.6
                tone = math.sin(2 * math.pi * 1200 * t) * 0.4
                sample = int(30000 * envelope * (noise + tone))
                sample = max(-32768, min(32767, sample))
                wav.writeframes(struct.pack("<h", sample))

    def _to_board_pos(self, event: tk.Event) -> tuple[int, int] | None:
        x = round((event.x - MARGIN) / CELL_SIZE)
        y = round((event.y - MARGIN) / CELL_SIZE)
        if not inside(x, y):
            return None
        px = MARGIN + x * CELL_SIZE
        py = MARGIN + y * CELL_SIZE
        if abs(event.x - px) > CELL_SIZE / 2 or abs(event.y - py) > CELL_SIZE / 2:
            return None
        return x, y

    def _on_click(self, event: tk.Event) -> None:
        if self.game_over:
            return

        if self.mode is None:
            self._set_status("请先选择模式。")
            return

        if self.mode == "remote" and not self.networked:
            self._set_status("请先建立远程联机。")
            return

        if self.networked and self.current_player != self.my_color:
            self._set_status("等待对方落子。")
            return

        pos = self._to_board_pos(event)
        if pos is None:
            return

        x, y = pos
        if self.board[y][x] != Stone.EMPTY:
            self._set_status("这里已经有棋子了。")
            return

        # 检测棋盘是否已满（平局）
        if all(self.board[y][x] != Stone.EMPTY for y in range(BOARD_SIZE) for x in range(BOARD_SIZE)):
            self.game_over = True
            self._set_status("棋盘已满，平局。")
            self._show_result_dialog("棋盘已满，平局！")
            self._update_cursor()
            return

        if self._apply_move(x, y, self.current_player):
            self._send_move_if_needed(x, y)

    def _draw_grid(self) -> None:
        self.canvas.delete("grid")
        board_end = MARGIN + CELL_SIZE * (BOARD_SIZE - 1)

        for i in range(BOARD_SIZE):
            pos = MARGIN + i * CELL_SIZE
            self.canvas.create_line(MARGIN, pos, board_end, pos, fill="#3c2f1e", width=1, tags="grid")
            self.canvas.create_line(pos, MARGIN, pos, board_end, fill="#3c2f1e", width=1, tags="grid")

        for x, y in ((3, 3), (3, 11), (7, 7), (11, 3), (11, 11)):
            cx = MARGIN + x * CELL_SIZE
            cy = MARGIN + y * CELL_SIZE
            self.canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill="#3c2f1e", outline="#3c2f1e", tags="grid")

    def _draw_stones(self) -> None:
        self.canvas.delete("stone")

        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                value = self.board[y][x]
                if value == Stone.EMPTY:
                    continue

                cx = MARGIN + x * CELL_SIZE
                cy = MARGIN + y * CELL_SIZE
                color = "#111111" if value == Stone.BLACK else "#f5f5f5"
                outline = "#000000" if value == Stone.BLACK else "#b6b6b6"
                self.canvas.create_oval(
                    cx - STONE_RADIUS,
                    cy - STONE_RADIUS,
                    cx + STONE_RADIUS,
                    cy + STONE_RADIUS,
                    fill=color,
                    outline=outline,
                    width=1,
                    tags="stone",
                )

        if self.last_move is not None:
            x, y = self.last_move
            cx = MARGIN + x * CELL_SIZE
            cy = MARGIN + y * CELL_SIZE
            self.canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill="#cc3d3d", outline="#cc3d3d", tags="stone")

    def _redraw(self) -> None:
        self.canvas.delete("all")
        self._draw_grid()
        self._draw_stones()

    def _apply_move(self, x: int, y: int, color: int, is_remote: bool = False) -> bool:
        self.board[y][x] = color
        if color == Stone.BLACK:
            result = check_black_move(self.board, x, y)
        else:
            result = check_white_move(self.board, x, y)

        if not result.legal:
            self.game_over = True
            winner = "白方" if color == Stone.BLACK else "黑方"
            final_message = f"{result.message} {winner}获胜。"
            self.last_move = (x, y)  # 标记禁手落子位置，显示红点
            self._record_move(x, y, color, False)
            self._set_status(final_message)
            self._redraw()  # 先绘制棋子
            self.canvas.update()  # 强制刷新画布，确保棋子可见
            # 远程落子时，发送端已经发送了 RESULT 和弹窗，接收端不再重复
            if not is_remote:
                self._show_result_dialog(final_message)
                self._send_result_if_needed(Stone.BLACK if winner == "黑方" else Stone.WHITE, final_message)
            self._handle_remote_game_end()
            self._update_cursor()
            return False

        self.last_move = (x, y)
        self._record_move(x, y, color, True)
        self._play_move_sound()
        self._redraw()

        if result.win:
            self.game_over = True
            self._set_status(result.message)
            # 远程落子时，发送端已经发送了 RESULT 和弹窗，接收端不再重复
            if not is_remote:
                self._show_result_dialog(result.message)
                self._send_result_if_needed(color, result.message)
            self._handle_remote_game_end()
            self._update_cursor()
            return True

        self.current_player = Stone.WHITE if color == Stone.BLACK else Stone.BLACK
        next_side = "黑方" if self.current_player == Stone.BLACK else "白方"
        self._set_status(f"轮到{next_side}。")
        return True

    def _send_result_if_needed(self, winner_color: int, message: str) -> None:
        if self.mode != "remote" or not self.networked:
            return
        winner = "BLACK" if winner_color == Stone.BLACK else "WHITE"
        safe_message = message.replace("\n", " ")
        self._send_net(f"RESULT|{self.session_id}|{winner}|{safe_message}")

    def _handle_remote_game_end(self) -> None:
        if self.mode != "remote" or not self.networked:
            return
        if not self.is_host:
            return

        self.remote_black_is_host = not self.remote_black_is_host
        owner = "HOST" if self.remote_black_is_host else "CLIENT"
        self._send_net(f"NEXTBLACK|{self.session_id}|{owner}")

    def _record_move(self, x: int, y: int, color: int, legal: bool) -> None:
        self.move_records.append(
            {
                "move": len(self.move_records) + 1,
                "color": "black" if color == Stone.BLACK else "white",
                "x": x,
                "y": y,
                "legal": legal,
                "time": datetime.now().isoformat(timespec="seconds"),
            }
        )

    def _send_move_if_needed(self, x: int, y: int) -> None:
        if not self.networked or self.net_socket is None:
            return
        # 在 MOVE 消息中包含颜色信息，避免接收方因状态不同步而推断错误
        color_str = "BLACK" if self.current_player == Stone.BLACK else "WHITE"
        self._send_net(f"MOVE|{self.session_id}|{x}|{y}|{color_str}")

    def _open_network_dialog(self) -> None:
        if self._network_dialog_open:
            # 窗口已打开：提升到最前、聚焦、抖动突出、播放系统提示音
            if self._network_dialog is not None:
                try:
                    exists = self._network_dialog.winfo_exists()
                except tk.TclError:
                    exists = False
                if exists:
                    self._network_dialog.lift()
                    self._network_dialog.focus_force()
                    # 系统提示音效
                    if winsound:
                        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                    else:
                        self.root.bell()
                    # 抖动效果：快速左右位移
                    def shake(count: int = 5) -> None:
                        if count <= 0 or not self._network_dialog_open:
                            return
                        try:
                            dx = 15 if count % 2 == 1 else -15
                            x = self._network_dialog.winfo_x() + dx
                            y = self._network_dialog.winfo_y()
                            self._network_dialog.geometry(f"+{x}+{y}")
                            self._network_dialog.after(50, lambda: shake(count - 1))
                        except tk.TclError:
                            pass
                    shake()
                    return
                else:
                    self._network_dialog_open = False
                    self._network_dialog = None
            else:
                self._network_dialog_open = False

        self._network_dialog_open = True

        dialog = tk.Toplevel(self.root)
        dialog.title("联机对战")
        dialog.resizable(False, False)
        self._network_dialog = dialog

        # 居中显示对话框
        dialog.update_idletasks()
        dw = dialog.winfo_width()
        dh = dialog.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - dw) // 2
        y = (sh - dh) // 2
        dialog.geometry(f"+{x}+{y}")

        def close_dialog() -> None:
            self._network_dialog_open = False
            self._network_dialog = None
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", close_dialog)

        tk.Label(dialog, text="主机地址:", font=("Microsoft YaHei", 10)).grid(row=0, column=0, padx=10, pady=(12, 6), sticky="e")
        host_entry = tk.Entry(dialog, width=18, font=("Microsoft YaHei", 10))
        host_entry.insert(0, "127.0.0.1")
        host_entry.grid(row=0, column=1, padx=6, pady=(12, 6))

        tk.Label(dialog, text="端口:", font=("Microsoft YaHei", 10)).grid(row=1, column=0, padx=10, pady=6, sticky="e")
        port_entry = tk.Entry(dialog, width=10, font=("Microsoft YaHei", 10))
        port_entry.insert(0, "5000")
        port_entry.grid(row=1, column=1, padx=6, pady=6, sticky="w")

        def start_host() -> None:
            try:
                port = int(port_entry.get())
            except ValueError:
                self._set_status("端口无效。")
                return
            close_dialog()
            self._start_host(port)

        def start_client() -> None:
            try:
                port = int(port_entry.get())
            except ValueError:
                self._set_status("端口无效。")
                return
            host = host_entry.get().strip() or "127.0.0.1"
            close_dialog()
            self._start_client(host, port)

        tk.Button(dialog, text="作为主机", command=start_host, font=("Microsoft YaHei", 10)).grid(row=2, column=0, padx=10, pady=12)
        tk.Button(dialog, text="加入对局", command=start_client, font=("Microsoft YaHei", 10)).grid(row=2, column=1, padx=10, pady=12)

    def _enter_local_mode(self) -> None:
        self._set_mode_local()
        self._show_start_dialog()

    def _enter_remote_mode(self) -> None:
        self._set_mode_remote()
        self._open_network_dialog()

    def _set_mode_local(self) -> None:
        self.mode = "local"
        self._disconnect_network()
        self._reset_game(show_dialog=False)
        self._set_status("已切换到本地双人模式。")

    def _set_mode_remote(self) -> None:
        self.mode = "remote"
        self._disconnect_network()
        self.remote_black_is_host = True
        self._reset_game(show_dialog=False)
        self._set_status("远程模式：请建立联机。")

    def _disconnect_network(self) -> None:
        self.networked = False
        self.is_host = False
        self.my_color = None
        self.peer_color = None
        self.protocol_ok = True
        with self._net_lock:
            if self.net_socket:
                try:
                    self.net_socket.close()
                except OSError:
                    pass
            self.net_socket = None

    def _start_host(self, port: int) -> None:
        if self.net_thread and self.net_thread.is_alive():
            self._set_status("联机正在进行中。")
            return

        self.is_host = True

        def host_thread() -> None:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("0.0.0.0", port))
            server.listen(1)
            self.net_queue.put(("STATUS", f"等待对方连接，端口 {port} ..."))
            conn, addr = server.accept()
            server.close()
            with self._net_lock:
                self.net_socket = conn
            self.net_queue.put(("CONNECTED", addr))
            self._start_receiver_thread()
            self._start_heartbeat()
            self.pending_start = True
            self._send_hello()

        self.net_thread = threading.Thread(target=host_thread, daemon=True)
        self.net_thread.start()

    def _start_client(self, host: str, port: int) -> None:
        if self.net_thread and self.net_thread.is_alive():
            self._set_status("联机正在进行中。")
            return

        self.is_host = False

        def client_thread() -> None:
            try:
                conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                conn.connect((host, port))
            except OSError:
                self.net_queue.put(("STATUS", "连接失败，请检查地址与端口。"))
                return
            with self._net_lock:
                self.net_socket = conn
            self.net_queue.put(("CONNECTED", (host, port)))
            self._start_receiver_thread()
            self._start_heartbeat()
            self.pending_start = True
            self._send_hello()

        self.net_thread = threading.Thread(target=client_thread, daemon=True)
        self.net_thread.start()

    def _start_heartbeat(self) -> None:
        """
        启动心跳保活线程。

        每 HEARTBEAT_INTERVAL 秒发送一次 PING，若超过 HEARTBEAT_TIMEOUT
        未收到任何消息则认为连接已断开。
        使用 _heartbeat_id 确保旧连接的心跳线程自动退出（防止线程泄漏）。
        """

        self._heartbeat_id += 1
        my_id = self._heartbeat_id

        def beat() -> None:
            while self.networked and my_id == self._heartbeat_id:
                with self._last_message_time_lock:
                    elapsed = time.monotonic() - self._last_message_time
                if elapsed > HEARTBEAT_TIMEOUT:
                    self.net_queue.put(("DISCONNECTED", "连接超时，对方可能已断开。"))
                    break
                self._send_net("PING")
                time.sleep(HEARTBEAT_INTERVAL)

        threading.Thread(target=beat, daemon=True).start()

    def _start_receiver_thread(self) -> None:
        def receive_loop() -> None:
            with self._net_lock:
                sock = self.net_socket
            if sock is None:
                self.net_queue.put(("DISCONNECTED", "连接已断开。"))
                return

            buffer: str = ""
            while True:
                try:
                    data = sock.recv(1024)
                except OSError:
                    self.net_queue.put(("DISCONNECTED", "连接已断开。"))
                    break
                if not data:
                    self.net_queue.put(("DISCONNECTED", "连接已断开。"))
                    break
                try:
                    buffer += data.decode("utf-8")
                except UnicodeDecodeError:
                    # 忽略无法解码的字节序列
                    continue
                with self._last_message_time_lock:
                    self._last_message_time = time.monotonic()
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    self.net_queue.put(("NET", line.strip()))

        threading.Thread(target=receive_loop, daemon=True).start()

    def _send_net(self, message: str) -> None:
        with self._net_lock:
            sock = self.net_socket
        if sock is None:
            return
        try:
            sock.sendall((message + "\n").encode("utf-8"))
        except OSError:
            self._set_status("发送失败，连接已断开。")

    def _process_network_queue(self) -> None:
        while True:
            try:
                kind, payload = self.net_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "STATUS":
                self._set_status(str(payload))
            elif kind == "CONNECTED":
                self.networked = True
                self._assign_remote_colors()
            elif kind == "DISCONNECTED":
                self._disconnect_network()
                self._set_status(str(payload))
            elif kind == "NET":
                self._handle_net_message(str(payload))

        self.root.after(100, self._process_network_queue)

    def _handle_net_message(self, message: str) -> None:
        # 心跳消息
        if message == "PING":
            self._send_net("PONG")
            return
        if message == "PONG":
            return

        if message.startswith("HELLO|"):
            parts = message.split("|")
            if len(parts) >= 5:
                try:
                    peer_version = int(parts[1])
                except ValueError:
                    peer_version = -1
                if peer_version != PROTOCOL_VERSION:
                    self.protocol_ok = False
                    self._set_status("联机版本不一致，请双方更新到同一版本。")
                    self._show_result_dialog("联机版本不一致，请双方更新到同一版本。")
                    self._disconnect_network()
                    return
                # 主机是权威方，决定谁执黑；客户端接受主机的设定
                if not self.is_host:
                    self.remote_black_is_host = parts[3] == "HOST"
                try:
                    peer_session = int(parts[4])
                except ValueError:
                    peer_session = self.session_id
                if peer_session > self.session_id:
                    self.session_id = peer_session
                    self._reset_game(show_dialog=False)
                if self.networked:
                    self._assign_remote_colors()
                if self.pending_start:
                    self._send_net("HELLO_ACK")
            return

        if message == "HELLO_ACK":
            if self.pending_start:
                self.pending_start = False
                self._send_net("START")
            return

        if message == "START":
            self.networked = True
            self._assign_remote_colors()
            self._reset_game(show_dialog=False)
            self._show_start_dialog()
            return

        if message.startswith("RESET|"):
            now = time.monotonic()
            if now - self.last_reset_at < self.reset_cooldown:
                return
            self.last_reset_at = now
            parts = message.split("|")
            if len(parts) >= 2:
                try:
                    incoming_session = int(parts[1])
                except ValueError:
                    incoming_session = self.session_id
                if incoming_session < self.session_id:
                    return
                self.session_id = incoming_session
            self._reset_game(show_dialog=False)
            self._show_start_dialog()
            return

        if message.startswith("RESULT|"):
            parts = message.split("|", 3)
            if len(parts) == 4:
                try:
                    incoming_session = int(parts[1])
                except ValueError:
                    incoming_session = self.session_id
                if incoming_session != self.session_id:
                    return
                winner = parts[2]
                result_message = parts[3]
                self.game_over = True
                self._set_status(result_message)
                self._show_result_dialog(result_message)
                self._update_cursor()
                if self.is_host:
                    self._handle_remote_game_end()
            return

        if message.startswith("NEXTBLACK|"):
            parts = message.split("|")
            if len(parts) == 3:
                try:
                    incoming_session = int(parts[1])
                except ValueError:
                    incoming_session = self.session_id
                if incoming_session != self.session_id:
                    return
                self.remote_black_is_host = parts[2] == "HOST"
                if self.networked:
                    self._assign_remote_colors()
            return

        if message.startswith("MOVE|"):
            parts = message.split("|")
            # 新格式: MOVE|session_id|x|y|color
            # 兼容旧格式: MOVE|session_id|x|y
            if len(parts) in (4, 5):
                try:
                    incoming_session = int(parts[1])
                    x = int(parts[2])
                    y = int(parts[3])
                except ValueError:
                    return
                if incoming_session != self.session_id:
                    return
                # 如果消息中包含颜色信息则使用它，否则回退到 current_player 推断
                if len(parts) == 5 and parts[4] in ("BLACK", "WHITE"):
                    color = Stone.BLACK if parts[4] == "BLACK" else Stone.WHITE
                else:
                    color = self.current_player
                if inside(x, y) and self.board[y][x] == Stone.EMPTY:
                    self._apply_move(x, y, color, is_remote=True)

    def _assign_remote_colors(self) -> None:
        if not self.networked:
            return

        if self.remote_black_is_host:
            self.my_color = Stone.BLACK if self.is_host else Stone.WHITE
        else:
            self.my_color = Stone.WHITE if self.is_host else Stone.BLACK
        self.peer_color = Stone.WHITE if self.my_color == Stone.BLACK else Stone.BLACK

        black_owner = "主机" if self.remote_black_is_host else "加入者"
        self._set_status(f"联机成功，本局黑方：{black_owner}。")

    def _send_hello(self) -> None:
        role = "HOST" if self.is_host else "CLIENT"
        black_owner = "HOST" if self.remote_black_is_host else "CLIENT"
        self._send_net(f"HELLO|{PROTOCOL_VERSION}|{role}|{black_owner}|{self.session_id}")

    def _save_record_dialog(self) -> None:
        if not self.move_records:
            self._set_status("暂无对局记录可保存。")
            return

        default_name = self.game_start_time.strftime("gomoku_%Y%m%d_%H%M%S.json")
        file_path = filedialog.asksaveasfilename(
            title="保存对局",
            defaultextension=".json",
            initialfile=default_name,
            filetypes=[("JSON 文件", "*.json")],
        )
        if not file_path:
            return

        data = {
            "start_time": self.game_start_time.isoformat(timespec="seconds"),
            "records": self.move_records,
        }
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._set_status("对局记录已保存。")
        except OSError:
            self._set_status("保存失败。")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = GomokuApp()
    app.run()


if __name__ == "__main__":
    main()
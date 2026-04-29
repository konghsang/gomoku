"""
Quick verification of forbidden move detection logic
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from gomoku import (
    BOARD_SIZE, Stone,
    count_black_three_targets, check_black_move
)


def set_cells(board, cells):
    for x, y in cells:
        board[y][x] = Stone.BLACK


def set_white(board, cells):
    for x, y in cells:
        board[y][x] = Stone.WHITE


tests_passed = 0
tests_failed = 0


def run_three_count(name, board, expected, desc):
    global tests_passed, tests_failed
    count = count_black_three_targets(board)
    ok = count == expected
    status = "OK" if ok else "FAIL"
    print(f"  [{status}] {name}: {desc}")
    print(f"         count={count} (expected={expected})")
    if ok: tests_passed += 1
    else: tests_failed += 1


def run_check(name, board, moves, expected_foul_type):
    """
    expected_foul_type: None (legal/win), "sansan", "sisi", "over", "five"
    """
    global tests_passed, tests_failed
    x, y = moves
    result = check_black_move(board, x, y)

    if expected_foul_type == "five":
        ok = result.win and result.legal
    elif expected_foul_type is None:
        ok = result.legal and not result.win
    elif expected_foul_type == "three":
        ok = not result.legal and "三三" in result.message
    elif expected_foul_type == "four":
        ok = not result.legal and "四四" in result.message
    elif expected_foul_type == "over":
        ok = not result.legal and "长连" in result.message
    else:
        ok = False

    status = "OK" if ok else "FAIL"
    r = "legal" if result.legal else f"foul({result.message})"
    e = expected_foul_type or "legal"
    if expected_foul_type == "five":
        e = "win(five)"
    print(f"  [{status}] {name}: result={r} (expected={e})")
    if ok: tests_passed += 1
    else: tests_failed += 1


print("=" * 60)
print("Forbidden move fix verification")
print("=" * 60)

# ================ Live-three vs Sleep-three ================
print("\n--- Live-three vs Sleep-three count tests ---")

# Test 1: Real live three - both sides >=2 empty
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(3, 7), (4, 7), (5, 7)])
run_three_count("1_live_three", board, 1, "both sides have >=2 empty cells")

# Test 2: Sleep three at top boundary
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(0, 0), (1, 0), (2, 0)])
run_three_count("2_sleep_top", board, 0, "touching top border - no extension upward")

# Test 3: Sleep three - left adjacent blocked by white
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(2, 7), (3, 7), (4, 7)])
set_white(board, [(1, 7)])
run_three_count("3_sleep_left_blocked", board, 0, "left adjacent blocked by white")

# Test 4: Sleep three - both adjacent blocked
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(2, 7), (3, 7), (4, 7)])
set_white(board, [(1, 7), (5, 7)])
run_three_count("4_sleep_both_adjacent", board, 0, "both adjacent cells occupied")

# Test 5: Sleep three - both extended cells blocked
# . . B B B . .  with white at (2-1=1) and (5+1=6) blocking the second space
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(3, 7), (4, 7), (5, 7)])
set_white(board, [(1, 7), (6, 7)])  # (2,7) empty, (1,7)=W; (6,7)=W
# Left: (2,7)=E(adj), (1,7)=W(blocked) -> backward_open2=False
# Right: (6,7)=W(adj blocked) -> forward_open=False (first check fails)
run_three_count("5_sleep_ext_blocked", board, 0, "both extension cells blocked by white")

# Test 6: Sleep three - one side can't extend (boundary)
# B B B . .  at left edge
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(0, 7), (1, 7), (2, 7)])
# Left: (-1,7) out of bounds -> first check `inside(prev_x, prev_y)` = False
# But wait: prev_x = 0-1 = -1, prev_y = 7 -> inside(-1,7) = False -> backward_open = False
# Condition: forward_open and backward_open -> forward_open=True, backward_open=False -> skip
# So count=0. Correct.
run_three_count("6_sleep_left_edge", board, 0, "touching left edge")

# Test 7: Sleep three - only one side has 2+ empty, other side blocked
# W . B B B . X  where W at (1,7) and X(out of bounds) at left side
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(2, 7), (3, 7), (4, 7)])
set_white(board, [(1, 7)])  # left adjacent blocked
# Right: (5,7)=E(adj), (6,7)=E(ext) -> forward_open2=True
# Left: (1,7)=W(adj blocked) -> backward_open=False -> first condition fails
# So count=0 because backward_open=False
run_three_count("7_sleep_right_limited", board, 0, "left adjacent blocked, right side has 2 empty but left fails first check")

# Wait - that's wrong. backward_open=False means the first condition `forward_open and backward_open` fails,
# so it never reaches the second check. Let me re-analyze:
# Three at (2,7)(3,7)(4,7). Black.
# forward: nx=5, ny=7 -> (5,7)=E -> forward_open=True
# backward: prev_x=1, prev_y=7 -> (1,7)=W -> backward_open=False
# Condition: forward_open and backward_open -> False -> skip this direction
# So count=0. Correct.

# Test 8: Live three - right side blocked but left side has 2+ empty
# This is actually a LIVE three because left side extends
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(3, 7), (4, 7), (5, 7)])
set_white(board, [(7, 7)])  # right second cell blocked
# Left: (2,7)=E(adj), (1,7)=E(ext) -> backward_open2=True -> LIVE THREE
run_three_count("8_live_three_unilateral", board, 1, "only one side has 2+ empty, still a live three")

# ================ check_black_move ================
print("\n--- check_black_move comprehensive tests ---")

# Test 9: Two live threes -> sansan forbidden
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(5, 7), (6, 7)])
set_cells(board, [(7, 5), (7, 6)])
board[7][7] = Stone.BLACK
run_check("9_sansan_double_live3", board, (7, 7), "three")

# Test 10: Five in a row wins (win takes priority)
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(1, 7), (2, 7), (3, 7), (4, 7)])
board[5][7] = Stone.BLACK
run_check("10_five_wins", board, (5, 7), "five")

# Test 11: Overline (6 in a row) -> forbidden
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(1, 7), (2, 7), (3, 7), (4, 7), (5, 7)])
board[6][7] = Stone.BLACK
run_check("11_overline_foul", board, (6, 7), "over")

# Test 12: Four-four -> forbidden
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(2, 7), (3, 7), (4, 7)])
set_cells(board, [(7, 2), (7, 3), (7, 4)])
board[5][7] = Stone.BLACK  # horizontal 4
board[7][5] = Stone.BLACK  # vertical 4
run_check("12_fourfour_foul", board, (7, 5), "four")

# Test 13: Live three + sleep three -> legal (NOT forbidden)
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
# Create a live three and sleep three, with the move completing both
# Vertical: (7,5)(7,6)[7,7] -> right side (7,8)(7,9) both empty -> live three
set_cells(board, [(7, 5), (7, 6)])
# Horizontal: (3,7)(4,7)(5,7) already exists at top boundary? no
# Use a sleep three at top edge: (0,0)(1,0)(2,0) is already 3
# That's sleep, but doesn't involve the new move
set_cells(board, [(0, 0), (1, 0), (2, 0)])  # existing sleep three (counts as 0)
board[7][7] = Stone.BLACK  # forms vertical live three
# After move: vertical live three count = 1, sleep three = 0, total = 1 -> legal
run_check("13_live3_sleep3_legal", board, (7, 7), None)

# Test 14: Overline on diagonal
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
for i in range(6):
    board[i][i] = Stone.BLACK
board[6][6] = Stone.BLACK  # 7 in a row on diagonal
run_check("14_overline_diagonal", board, (6, 6), "over")

# Test 15: Four in a row with extensions -> four-four
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(5, 7), (6, 7), (7, 7)])  # horizontal 3
board[8][7] = Stone.BLACK  # forms horizontal 4 at (5,7)(6,7)(7,7)[8,7]
# Need another 4 somewhere else
set_cells(board, [(2, 7), (2, 8), (2, 9)])  # vertical 3
board[2][10] = Stone.BLACK  # forms vertical 4 at (2,7)(2,8)(2,9)[2,10]
run_check("15_fourfour", board, (8, 7), "four")

print("\n" + "=" * 60)
print(f"Results: {tests_passed} passed, {tests_failed} failed")
print("=" * 60)
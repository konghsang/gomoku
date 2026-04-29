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


def run_three_count(name, board, place_x, place_y, expected, desc):
    global tests_passed, tests_failed
    count = count_black_three_targets(board, place_x, place_y)
    ok = count == expected
    status = "OK" if ok else "FAIL"
    print(f"  [{status}] {name}: {desc}")
    print(f"         count={count} (expected={expected}), place=({place_x},{place_y})")
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
run_three_count("1_live_three", board, 4, 7, 1, "both sides have >=2 empty cells")

# Test 2: Sleep three at top boundary
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(0, 0), (1, 0), (2, 0)])
run_three_count("2_sleep_top", board, 1, 0, 0, "touching top border - no extension upward")

# Test 3: Sleep three - left adjacent blocked by white
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(2, 7), (3, 7), (4, 7)])
set_white(board, [(1, 7)])
run_three_count("3_sleep_left_blocked", board, 3, 7, 0, "left adjacent blocked by white")

# Test 4: Sleep three - both adjacent blocked
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(2, 7), (3, 7), (4, 7)])
set_white(board, [(1, 7), (5, 7)])
run_three_count("4_sleep_both_adjacent", board, 3, 7, 0, "both adjacent cells occupied")

# Test 5: Sleep three - both extended cells blocked
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(3, 7), (4, 7), (5, 7)])
set_white(board, [(1, 7), (6, 7)])
run_three_count("5_sleep_ext_blocked", board, 4, 7, 0, "both extension cells blocked by white")

# Test 6: Sleep three - left edge
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(0, 7), (1, 7), (2, 7)])
run_three_count("6_sleep_left_edge", board, 1, 7, 0, "touching left edge")

# Test 7: Sleep three - left adjacent blocked
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(2, 7), (3, 7), (4, 7)])
set_white(board, [(1, 7)])
run_three_count("7_sleep_right_limited", board, 3, 7, 0, "left adjacent blocked")

# Test 8: Live three - right side blocked but left side has 2+ empty
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(3, 7), (4, 7), (5, 7)])
set_white(board, [(7, 7)])
run_three_count("8_live_three_unilateral", board, 4, 7, 1, "only one side has 2+ empty, still a live three")

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

# Test 12: Four-four -> forbidden (both 4s must involve the move point)
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
# Vertical 4 at x=7: (7,4)(7,5)(7,6)[7,7]
set_cells(board, [(7, 4), (7, 5), (7, 6)])
# Horizontal 4 at y=7: (4,7)(5,7)(6,7)[7,7]
set_cells(board, [(4, 7), (5, 7), (6, 7)])
board[7][7] = Stone.BLACK  # move at (7,7) completes both 4s
run_check("12_fourfour_foul", board, (7, 7), "four")

# Test 13: Live three + sleep three -> legal (NOT forbidden)
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
# Vertical: (7,5)(7,6)[7,7] -> right side (7,8)(7,9) both empty -> live three
set_cells(board, [(7, 5), (7, 6)])
# Sleep three at top edge: (0,0)(1,0)(2,0) is sleep three (counts as 0)
set_cells(board, [(0, 0), (1, 0), (2, 0)])
board[7][7] = Stone.BLACK  # forms vertical live three only (sleep three doesn't count)
run_check("13_live3_sleep3_legal", board, (7, 7), None)

# Test 14: Overline on diagonal
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
for i in range(6):
    board[i][i] = Stone.BLACK
board[6][6] = Stone.BLACK  # 7 in a row on diagonal
run_check("14_overline_diagonal", board, (6, 6), "over")

# Test 15: Four-four on two lines crossing at move point -> four-four
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
# Vertical 4 at x=7: (7,3)(7,4)(7,5)(7,6)[7,7] (need 4 pre, move at (7,7) makes 5 - that's a five!)
# Instead: have the move form two 4s with pre-existing 3s
# Anti-diagonal 4: (10,5)(9,6)(8,7)[7,8] no... 
# Simpler: move at (9,7), horizontal 4 and vertical 4
# Vertical 3: (9,4)(9,5)(9,6) + move at (9,7) = 4
# Horizontal 3: (6,7)(7,7)(8,7) + move at (9,7) = 4
set_cells(board, [(9, 4), (9, 5), (9, 6)])    # vertical 3 at x=9
set_cells(board, [(6, 7), (7, 7), (8, 7)])    # horizontal 3 at y=7
board[7][9] = Stone.BLACK  # move at (9,7): completes both 4s
run_check("15_fourfour", board, (9, 7), "four")

# ================ New Tests: Five vs Overline priority ================
print("\n--- Five vs Overline priority tests ---")

# Test 16: Five + overline simultaneously (cross pattern) -> five wins
# Horizontal: 5 in a row, Vertical: 6 in a row, cross at (7,7)
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
# Horizontal 5: (3,7)(4,7)(5,7)(6,7)[7,7] -> 5 total
# Vertical 6: (7,2)(7,3)(7,4)(7,5)(7,6)[7,7] -> 6 total
set_cells(board, [(3, 7), (4, 7), (5, 7), (6, 7)])  # horizontal 4
set_cells(board, [(7, 2), (7, 3), (7, 4), (7, 5), (7, 6)])  # vertical 5
board[7][7] = Stone.BLACK  # completes both: horizontal 5 + vertical 6
run_check("16_five_beats_overline_cross", board, (7, 7), "five")

# Test 17: Five + overline on same line at edge -> five wins
# Edge case: (10,7) to (14,7) is 5 black, (15,7) would be outside -> 
# Instead: (0,7)(1,7)(2,7)(3,7)(4,7)(5,7) = 6 in a row, break it differently
# Use: five at (0,7)(1,7)(2,7)(3,7)[4,7] = 5, forming a natural 5
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(0, 7), (1, 7), (2, 7), (3, 7)])
board[4][7] = Stone.BLACK  # forms 5 in a row
# No overline here, just testing baseline five detection
run_check("17_five_detection_baseline", board, (4, 7), "five")

# Test 18: Five + live three simultaneously (five beats sansan) -> five wins
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
# Horizontal 5: (3,7)(4,7)(5,7)(6,7)[7,7]
set_cells(board, [(3, 7), (4, 7), (5, 7), (6, 7)])  # horizontal 4
# Vertical live 3: (7,5)(7,6)[7,7] -> empty at (7,4) and (7,8), (7,3) and (7,9) both empty -> live 3
set_cells(board, [(7, 5), (7, 6)])  # vertical 2
board[7][7] = Stone.BLACK  # completes horizontal 5 AND vertical live 3
run_check("18_five_beats_sansan", board, (7, 7), "five")  # five wins over sansan

# Test 19: Five + four-four simultaneously -> five wins
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
# Horizontal 4: (2,7)(3,7)(4,7)[5,7] -> move at (5,7) completes horizontal 5
set_cells(board, [(2, 7), (3, 7), (4, 7)])
set_cells(board, [(1, 7)])  # this makes horizontal 5 at (1,7)(2,7)(3,7)(4,7)[5,7]
# Actually no, just use (0,7)(1,7)(2,7)(3,7) and move at (4,7) -> 5 
# But we need another 4 somewhere
# Let me use a different approach
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(1, 7), (2, 7), (3, 7), (4, 7)])
# Move at (5,7) forms 5 in a row
board[5][7] = Stone.BLACK
# Already 5 in a row, but no second four - let's add one via a different line
# Actually this is (1,7)(2,7)(3,7)(4,7)[5,7] = 5, no four-four here
# For a proper test: make move that forms five AND a four simultaneously
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
# Set up: horizontal 4 at (2,7) through (5,7), move at (6,7) completes 5
set_cells(board, [(2, 7), (3, 7), (4, 7), (5, 7)])
# Set up: vertical three at (7,2)(7,3)(7,4), move at (7,5) would be a four
# But we want ONE move that creates both:
# Horizontal: (2,7)(3,7)(4,7)(5,7)[6,7] = 5 
# Vertical: (7,2)(7,3)(7,4)[7,5] is a 4 but doesn't involve (6,7)
# This won't work. Let me try (1,7) as the move point
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
# Horizontal: already 5? No, set 4 blacks, move makes 5 AND a second 4
# Move at (7,7):
# Horizontal: (6,7)[7,7] = 2, not 5. Bad.
# Let me think differently. Have 4 blacks in a line forming into 5, 
# and also 3 blacks in another line forming into 4 (a 4, not 5)
# At (7,7): horizontal 5 and vertical 4 or diagonal 4
# Horizontal: (3,7)(4,7)(5,7)(6,7)[7,7] = 5
# Vertical: (7,4)(7,5)(7,6)[7,7] = 4 (need exactly 4)
set_cells(board, [(3, 7), (4, 7), (5, 7), (6, 7)])  # horizontal 4
set_cells(board, [(7, 4), (7, 5), (7, 6)])          # vertical 3
board[7][7] = Stone.BLACK  # horizontal 5 + vertical 4
# This is five + 4, NOT five + four-four (need 2x fours)
# Still good test: five should win
run_check("19_five_beats_four_and_overline", board, (7, 7), "five")

# Test 20: Overline ONLY (7 in a row, 6 counts is overline)
# 7 blacks: (0,7)(1,7)(2,7)(3,7)(4,7)(5,7)[6,7]
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(0, 7), (1, 7), (2, 7), (3, 7), (4, 7), (5, 7)])
board[7][6] = Stone.BLACK  # move at (6,7) -> 7 in a row
run_check("20_overline_only", board, (6, 7), "over")

# ================ New Tests: Place-specific counting ================
print("\n--- Place-specific counting tests ---")

# Test 21: Pre-existing live three + new live three from same move -> sansan
# But both threes must involve the move point
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
# Existing live three NOT involving (7,7): e.g. (1,1)(2,1)(3,1) - but this shouldn't count
# New live three #1 from (7,7): vertical (7,5)(7,6)[7,7]
# New live three #2 from (7,7): horizontal (5,7)(6,7)[7,7]
set_cells(board, [(7, 5), (7, 6)])   # vertical pre
set_cells(board, [(5, 7), (6, 7)])   # horizontal pre
board[7][7] = Stone.BLACK  # forms 2 live threes, both involve (7,7)
run_check("21_sansan_both_involve_move", board, (7, 7), "three")

# Test 22: Pre-existing live three (unrelated) + 1 new live three -> legal
# The existing live three doesn't involve the move point, so only 1 count
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
# Existing live three at (0,0)(0,1)(0,2) - doesn't involve (7,7)
set_cells(board, [(0, 0), (0, 1), (0, 2)])
# One new live three from (7,7): vertical (7,5)(7,6)[7,7]
set_cells(board, [(7, 5), (7, 6)])
board[7][7] = Stone.BLACK
# count_black_three_targets(board, 7, 7) should = 1 (only vertical)
run_check("22_existing_live3_not_counted", board, (7, 7), None)

# Test 23: Pre-existing four (unrelated) + 1 new four -> four-four
# BOTH fours must involve the move point
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
# Existing four that DOESN'T involve (7,7): (0,0)(0,1)(0,2)(0,3)
set_cells(board, [(0, 0), (0, 1), (0, 2), (0, 3)])
# New four from (7,7): vertical (7,4)(7,5)(7,6)[7,7]
set_cells(board, [(7, 4), (7, 5), (7, 6)])
board[7][7] = Stone.BLACK
# count_black_four_targets(board, 7, 7) should = 1 (only vertical)
run_check("23_existing_four_not_counted", board, (7, 7), None)

print("\n" + "=" * 60)
print(f"Results: {tests_passed} passed, {tests_failed} failed")
print("=" * 60)
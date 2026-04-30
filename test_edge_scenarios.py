"""
Edge case tests for the user's reported issue:
'原来有一个四三 我再下一子 形成四四 这个就不违反规则'

This tests various scenarios where a pre-existing 4 or 3 exists on the board,
and a new move creates additional 4s or 3s, checking that the forbidden move
detection correctly handles the "该落子必须在每一个四中/三中" rule.
"""
import sys
from gomoku import (
    BOARD_SIZE, Stone,
    count_black_four_targets, count_black_three_targets,
    check_black_move, line_has_exact_five, line_has_overline
)


def set_cells(board, cells):
    for x, y in cells:
        board[y][x] = Stone.BLACK


tests_passed = 0
tests_failed = 0


def run_four_count(name, board, px, py, expected, desc):
    global tests_passed, tests_failed
    count = count_black_four_targets(board, px, py)
    ok = count == expected
    status = "OK" if ok else "FAIL"
    print(f"  [{status}] {name}: four_targets={count} (expected={expected}), place=({px},{py})")
    if not ok:
        print(f"         DESC: {desc}")
    if ok: tests_passed += 1
    else: tests_failed += 1


def run_check(name, board, move, expected, desc=""):
    """
    expected: None=legal, "three"=三三, "four"=四四, "five"=五连, "over"=长连
    """
    global tests_passed, tests_failed
    x, y = move
    # 模拟实际落子流程：先放置棋子再检测禁手
    #（与 _apply_move 中的 board[y][x] = color; check_black_move(board, x, y) 逻辑一致）
    board[y][x] = Stone.BLACK
    result = check_black_move(board, x, y)

    if expected == "five":
        ok = result.win and result.legal
    elif expected is None:
        ok = result.legal and not result.win
    elif expected == "three":
        ok = not result.legal and "三三" in result.message
    elif expected == "four":
        ok = not result.legal and "四四" in result.message
    elif expected == "over":
        ok = not result.legal and "长连" in result.message
    else:
        ok = False

    status = "OK" if ok else "FAIL"
    r = "legal" if result.legal else f"foul({result.message})"
    e = expected or "legal"
    print(f"  [{status}] {name}: result={r} (expected={e})")
    if not ok:
        print(f"         DESC: {desc}")
    if ok: tests_passed += 1
    else: tests_failed += 1


print("=" * 70)
print("Edge case tests: pre-existing 4/3 + new move creating 4s/3s")
print("=" * 70)

# ====================================================================
# Section 1: 四三 → 形成四四 (user's reported scenario)
# The board already has a 四三 (one 4 and one 3).
# Player makes a move. The key question: does forming 四四 from this
# position violate the rules?
#
# Understanding: The 4 in '四三' is a pre-existing four on the board.
# If that pre-existing four does NOT contain the move point, it should
# NOT be counted toward 四四 detection. Only the new 4(s) formed BY
# the move that CONTAIN the move point should be counted.
#
# So: pre-existing-4(non-intersecting) + pre-existing-3 + move(3→4)
#     = only 1 four involving the move point → legal (no 四四)
# ====================================================================

print("\n--- Scenario A: Pre-existing 四三, move creates 四四 (should be LEGAL) ---")

# A1: Pre-existing 4 at (0,0)(0,1)(0,2)(0,3) - independent, NOT involving (7,7)
#     Pre-existing 3 at (7,4)(7,5)(7,6) - extending to (7,7) = 4 with move
#     Move at (7,7): only 1 four involves (7,7). No 四四!
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(0,0), (0,1), (0,2), (0,3)])  # independent 4
set_cells(board, [(7,4), (7,5), (7,6)])           # 3 that becomes 4
board[7][7] = Stone.BLACK  # move
run_four_count("A1_independent_4+three→four", board, 7, 7, 1,
    "pre-existing 4 elsewhere + 3→4 = 1 four involving move point")

# A2: Same as A1 but as a check_black_move test
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(0,0), (0,1), (0,2), (0,3)])
set_cells(board, [(7,4), (7,5), (7,6)])
run_check("A2_independent_four+one_new_four_legal", board, (7,7), None,
    "independent pre-existing 4 + new 4 from 3 = 1 four, legal")

# A3: Pre-existing 4 at one end, pre-existing 3 at other end, 
#     both through the same line! Move connects them:
#     (0,7)(1,7)(2,7)(3,7) + move(4,7) + (5,7)(6,7)(7,7)???
#     That would make length 8, not 4. Bad test. Skip.

# A4: Pre-existing 4 (horizontal) at y=0, pre-existing 3 (horizontal at y=7) that becomes 4,
#     PLUS pre-existing 3 (diagonal) that ALSO becomes 4 with the same move = 2 fours
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(0,0), (0,1), (0,2), (0,3)])  # independent 4 (NOT involving move)
set_cells(board, [(7,4), (7,5), (7,6)])           # vertical 3 → 4
set_cells(board, [(4,7), (5,7), (6,7)])           # horizontal 3 → 4
run_check("A4_independent_four_TWO_new_fours_fourfour", board, (7,7), "four",
    "independent 4 + two new 4s = 四四 forbidden (2 fours involve move point)")

print("\n--- Scenario B: 四三 in same line, move extends both (five wins) ---")

# B1: Pre-existing 4 that extends through move point to become 5
#     Pre-existing 3 that extends through move point to become 4
#     Result: FIVE wins (5 takes priority over anything)
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(3,7), (4,7), (5,7), (6,7)])  # 4 that becomes 5
set_cells(board, [(7,4), (7,5), (7,6)])           # 3 that becomes 4
run_check("B1_four_plus_three_at_move_five_wins", board, (7,7), "five",
    "4→5 + 3→4 at same move: FIVE wins")

print("\n--- Scenario C: Pre-existing 四 and independently forming two new 3s ---")

# C1: Pre-existing independent 4 elsewhere + move creates 2 new live-3s → 三三
#     (三三 detection should also only count 3s involving move point)
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(0,0), (0,1), (0,2), (0,3)])  # independent 4
set_cells(board, [(7,5), (7,6)])          # vertical 2 → 3
set_cells(board, [(5,7), (6,7)])          # horizontal 2 → 3
run_check("C1_independent_four_two_new_live3_sansan", board, (7,7), "three",
    "independent 4 + 2 new live-3s = 三三 forbidden")

# C2: Pre-existing 三+三 (both involving move) + pre-existing 4 elsewhere
#     → this should still be 三三 (the 4 doesn't affect 三三 detection)
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(7,5), (7,6)])          # vertical 2 → 3
set_cells(board, [(5,7), (6,7)])          # horizontal 2 → 3
set_cells(board, [(0,0), (0,1), (0,2), (0,3)])  # independent 4
run_check("C2_two_live3_sansan_not_affected_by_independent_four", board, (7,7), "three",
    "2 new 3s = 三三, independent 4 doesn't matter")

# ====================================================================
# Section 2: Pre-existing 4 that DOES involve the move point
# If the board has a 4 that involves the move point (i.e. endpoint of the 4
# is where we'll play), and we play there extending it to 5, it's a FIVE win.
# ====================================================================

print("\n--- Scenario D: Pre-existing 4 involving move point (becomes 5) ---")

# D1: Simple: (3,7)(4,7)(5,7)(6,7) + move(7,7) = 5
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(3,7), (4,7), (5,7), (6,7)])
run_check("D1_four_becomes_five", board, (7,7), "five",
    "4→5: five wins")

# D2: The 4 extends to 5, AND another 3 extends to 4 = still five wins
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(3,7), (4,7), (5,7), (6,7)])  # horizontal 4 → 5
set_cells(board, [(7,4), (7,5), (7,6)])           # vertical 3 → 4
run_check("D2_five_beats_fourfour_too", board, (7,7), "five",
    "4→5 + 3→4 = five wins over 四四")

# ====================================================================
# Section 3: Two independent fours + move creating ONE four
# ====================================================================

print("\n--- Scenario E: Two pre-existing independent 4s + move creates a 3rd? ---")

# E1: Two 4s elsewhere, move creates 1 new 4 = still only 1 four involving move point → legal
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(0,0), (0,1), (0,2), (0,3)])  # 4 #1
set_cells(board, [(0,5), (0,6), (0,7), (0,8)])  # 4 #2 (y=0 already has 0,1,2,3 and 5,6,7,8)
# Actually those are separate 4s on same row (gap at x=4)
# Let me use different rows
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(0,0), (0,1), (0,2), (0,3)])  # 4 #1 at y=0
set_cells(board, [(1,0), (1,1), (1,2), (1,3)])  # 4 #2 at y=1
set_cells(board, [(7,4), (7,5), (7,6)])           # 3 → 4 at x=7
run_check("E1_two_independent_fours_one_new_four_legal", board, (7,7), None,
    "2 pre-existing 4s (not involving move) + 1 new 4 = legal")

# ====================================================================
# Section 4: Verify that the SAME line segment isn't double-counted
# ====================================================================

print("\n--- Scenario F: Ensuring no double-counting of same segment ---")

# F1: Vertical 3 + horizontal 3 at cross → move forms two 4s → 四四
# Vertical: (7,4)(7,5)(7,6)[7,7] = 4 stones (a four)
# Horizontal: (4,7)(5,7)(6,7)[7,7] = 4 stones (another four)
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(7,4), (7,5), (7,6)])  # vertical 3 → becomes 4 with move
set_cells(board, [(4,7), (5,7), (6,7)])  # horizontal 3 → becomes 4 with move
run_check("F1_two_fours_at_cross", board, (7,7), "four",
    "vertical 3 + horizontal 3 at cross = 2 fours = 四四")

# F2: Independent 4 + vertical 3 + horizontal 3 at cross = 2 new fours = 四四
# The independent 4 doesn't involve (7,7) so it doesn't count.
# But vertical + horizontal each become 4 = 2 fours involving (7,7) = 四四
board = [[Stone.EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
set_cells(board, [(0,0), (0,1), (0,2), (0,3)])  # independent 4 (not involving move)
set_cells(board, [(7,4), (7,5), (7,6)])  # vertical 3 → 4
set_cells(board, [(4,7), (5,7), (6,7)])  # horizontal 3 → 4
run_check("F2_independent_four_plus_two_new_fours", board, (7,7), "four",
    "independent 4 + 2 new fours = 四四 (the 2 fours involving move point)")


print("\n" + "=" * 70)
print(f"Final Results: {tests_passed} passed, {tests_failed} failed")
print("=" * 70)

if tests_failed > 0:
    sys.exit(1)
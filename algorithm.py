"""
algorithm.py
============
Core AI logic for the Exam Seating Arrangement System.

Two classic techniques are combined:

1. GRAPH COLORING (Welsh-Powell greedy heuristic)
   - Every student is a VERTEX.
   - An EDGE joins two students that must NOT sit next to each other
     (same department and/or same subject, depending on the rules chosen).
   - Vertices are colored so that adjacent vertices get different colors.
     Each color class is a set of mutually "safe" students.  The colors are
     used (a) to order the search for the backtracking step and
     (b) to visualise the conflict groups.

2. BACKTRACKING (constraint satisfaction search)
   - Seats are filled one by one (row-major, hall after hall).
   - For each seat we try a candidate student; the candidate is accepted only
     if it has no conflict edge with any already-seated horizontal or vertical
     neighbour.
   - If no candidate fits, we undo (backtrack) the previous decision and try
     the next alternative.
   - Symmetry pruning: students with identical attributes are
     interchangeable, so only one representative of each "profile" is tried
     per seat. This keeps the search fast for hundreds of students.

No randomness is used: the result is fully deterministic and validated.
"""

from collections import defaultdict


# ---------------------------------------------------------------------------
# 1. Conflict graph
# ---------------------------------------------------------------------------
def is_conflict(a, b, rules):
    """Return True if students a and b must not be seated adjacently."""
    if a["id"] == b["id"]:
        return False
    if rules.get("department") and a["department"] == b["department"]:
        return True
    if rules.get("subject") and a["subject"] == b["subject"]:
        return True
    if rules.get("year") and a["year"] == b["year"] and a["department"] == b["department"]:
        return True
    return False


def build_conflict_graph(students, rules):
    """
    Build an adjacency-list graph: {student_id: set(conflicting_student_ids)}.
    O(n^2) pairwise comparison - fine for college-sized data.
    """
    graph = {s["id"]: set() for s in students}
    for i in range(len(students)):
        for j in range(i + 1, len(students)):
            a, b = students[i], students[j]
            if is_conflict(a, b, rules):
                graph[a["id"]].add(b["id"])
                graph[b["id"]].add(a["id"])
    return graph


# ---------------------------------------------------------------------------
# 2. Graph coloring (Welsh-Powell)
# ---------------------------------------------------------------------------
def graph_coloring(graph):
    """
    Welsh-Powell greedy coloring:
      1. Sort vertices by degree (most conflicts first).
      2. Give each vertex the smallest color not used by its neighbours.
    Returns {student_id: color_index}.
    """
    order = sorted(graph, key=lambda v: len(graph[v]), reverse=True)
    color = {}
    for v in order:
        used = {color[n] for n in graph[v] if n in color}
        c = 0
        while c in used:
            c += 1
        color[v] = c
    return color


# ---------------------------------------------------------------------------
# 3. Seat conflict check
# ---------------------------------------------------------------------------
def neighbours(r, c, rows, cols):
    """Horizontal + vertical neighbours of seat (r, c)."""
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            yield nr, nc


def check_seat_conflict(student, hall_idx, r, c, grid, halls, by_id, rules):
    """True if placing `student` at (hall, r, c) conflicts with a neighbour."""
    h = halls[hall_idx]
    for nr, nc in neighbours(r, c, h["rows"], h["cols"]):
        other = grid[hall_idx][nr][nc]
        if other is not None and is_conflict(student, by_id[other], rules):
            return True
    return False


# ---------------------------------------------------------------------------
# 4. Backtracking seat allocation
# ---------------------------------------------------------------------------
class AllocationError(Exception):
    pass


def backtracking_allocation(students, halls, rules, max_steps=500000):
    """
    Assign every student a seat so that no two conflicting students are
    horizontal/vertical neighbours.

    Returns list of dicts: {student_id, hall_id, row, col, color}.
    Raises AllocationError if impossible / capacity insufficient.
    """
    capacity = sum(h["rows"] * h["cols"] for h in halls)
    if not students:
        raise AllocationError("No students found for the selected exam session.")
    if capacity < len(students):
        raise AllocationError(
            f"Insufficient seats: {len(students)} students but only {capacity} seats available."
        )

    graph = build_conflict_graph(students, rules)
    colors = graph_coloring(graph)
    by_id = {s["id"]: s for s in students}

    # Group interchangeable students by profile (symmetry pruning)
    def profile(s):
        return (s["department"], s["subject"], s["year"])

    pools = defaultdict(list)
    for s in sorted(students, key=lambda s: (colors[s["id"]], s["register_no"])):
        pools[profile(s)].append(s["id"])

    seats = [(hi, r, c) for hi, h in enumerate(halls)
             for r in range(h["rows"]) for c in range(h["cols"])]
    grid = [[[None] * h["cols"] for _ in range(h["rows"])] for h in halls]
    remaining = [len(students)]
    steps = [0]

    def solve(k):
        if remaining[0] == 0:
            return True
        if k >= len(seats):
            return False
        # Prune: not enough seats left for remaining students
        if len(seats) - k < remaining[0]:
            return False
        steps[0] += 1
        if steps[0] > max_steps:
            raise AllocationError(
                "Search limit reached - constraints are too strict for the available halls. "
                "Add more halls or relax the rules."
            )
        hi, r, c = seats[k]
        # Candidate order: profile with most students left first (fail-first),
        # ties broken by graph colour.
        cand = sorted((p for p in pools if pools[p]),
                      key=lambda p: (-len(pools[p]), colors[pools[p][0]]))
        for p in cand:
            sid = pools[p][-1]
            if check_seat_conflict(by_id[sid], hi, r, c, grid, halls, by_id, rules):
                continue
            # choose
            pools[p].pop()
            grid[hi][r][c] = sid
            remaining[0] -= 1
            if solve(k + 1):
                return True
            # backtrack
            remaining[0] += 1
            grid[hi][r][c] = None
            pools[p].append(sid)
        # Option: leave this seat empty (only if spare seats exist)
        if len(seats) - k - 1 >= remaining[0]:
            if solve(k + 1):
                return True
        return False

    import sys
    sys.setrecursionlimit(max(10000, len(seats) * 3 + 100))
    if not solve(0):
        raise AllocationError(
            "No valid arrangement exists with the current rules and halls. "
            "Add more halls or relax the rules."
        )

    result = []
    for hi, h in enumerate(halls):
        for r in range(h["rows"]):
            for c in range(h["cols"]):
                sid = grid[hi][r][c]
                if sid is not None:
                    result.append({"student_id": sid, "hall_id": h["id"],
                                   "row": r + 1, "col": c + 1, "color": colors[sid]})
    validate_arrangement(result, students, halls, rules)
    return result


# ---------------------------------------------------------------------------
# 5. Final validation
# ---------------------------------------------------------------------------
def validate_arrangement(result, students, halls, rules):
    """Independently verify the final arrangement. Raises AllocationError."""
    by_id = {s["id"]: s for s in students}
    hall_map = {h["id"]: h for h in halls}
    seen_students, seen_seats = set(), set()
    pos = {}
    for a in result:
        if a["student_id"] in seen_students:
            raise AllocationError("Validation failed: duplicate student allocation.")
        key = (a["hall_id"], a["row"], a["col"])
        if key in seen_seats:
            raise AllocationError("Validation failed: duplicate seat allocation.")
        h = hall_map[a["hall_id"]]
        if not (1 <= a["row"] <= h["rows"] and 1 <= a["col"] <= h["cols"]):
            raise AllocationError("Validation failed: seat outside hall capacity.")
        seen_students.add(a["student_id"])
        seen_seats.add(key)
        pos[key] = a["student_id"]
    if len(seen_students) != len(students):
        raise AllocationError("Validation failed: some students were not seated.")
    for (hid, r, c), sid in pos.items():
        for nr, nc in ((r + 1, c), (r, c + 1)):
            other = pos.get((hid, nr, nc))
            if other and is_conflict(by_id[sid], by_id[other], rules):
                raise AllocationError("Validation failed: conflicting neighbours found.")
    return True

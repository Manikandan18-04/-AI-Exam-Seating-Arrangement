# AI-Based Exam Seating Arrangement (Graph Coloring + Backtracking)

## Run on Windows
1. Install Python 3.10+ (tick "Add Python to PATH").
2. Double-click `run.bat`  (or run manually):
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   python init_db.py        (optional - app.py creates the DB automatically)
   python app.py
   ```
3. Open http://127.0.0.1:5000 and log in with **admin / admin123**.

The database is created with 80 sample students (CSE, ECE, MECH, IT, EEE), 4 exams on
2026-12-01 Morning and 3 halls. Go to **Generate Seating** -> Run Algorithm.
To reset everything, delete `exam_seating.db` and restart.

## Folder structure
```
app.py            Flask routes (login, CRUD, generation, reports)
algorithm.py      Conflict graph, Welsh-Powell coloring, backtracking, validation
database.py       SQLite schema + initialization + sample data loader
init_db.py        Stand-alone DB initialization script
sample_data/      sample_students.csv (also usable for the CSV upload)
templates/        Bootstrap HTML pages
static/           CSS + JS
```

## Algorithm (algorithm.py)
| Function | Purpose |
|---|---|
| `build_conflict_graph` | Students = vertices, edge when same department / subject (configurable) |
| `check_seat_conflict` | Checks horizontal + vertical neighbours of a seat |
| `graph_coloring` | Welsh-Powell greedy coloring of the conflict graph |
| `backtracking_allocation` | Fills seats one by one, undoes choices on conflict |
| `validate_arrangement` | Independently verifies duplicates, capacity, adjacency |

## Database tables
admin, students, exams, examination_halls, seat_allocations (FKs to students, exams, halls).

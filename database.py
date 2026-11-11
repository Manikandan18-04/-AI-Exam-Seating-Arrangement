"""Database helpers and initialization (SQLite)."""
import os
import sqlite3
import csv
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "exam_seating.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS admin (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    department TEXT NOT NULL,
    year INTEGER NOT NULL,
    subject TEXT NOT NULL,
    register_no TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    subject TEXT NOT NULL,
    exam_date TEXT NOT NULL,
    session TEXT NOT NULL CHECK (session IN ('Morning','Afternoon')),
    num_students INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS examination_halls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hall_name TEXT NOT NULL,
    hall_number TEXT UNIQUE NOT NULL,
    rows INTEGER NOT NULL,
    cols INTEGER NOT NULL,
    capacity INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS seat_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_date TEXT NOT NULL,
    session TEXT NOT NULL,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    exam_id INTEGER REFERENCES exams(id) ON DELETE CASCADE,
    hall_id INTEGER NOT NULL REFERENCES examination_halls(id) ON DELETE CASCADE,
    row_no INTEGER NOT NULL,
    col_no INTEGER NOT NULL,
    color INTEGER NOT NULL DEFAULT 0,
    UNIQUE (exam_date, session, hall_id, row_no, col_no),
    UNIQUE (exam_date, session, student_id)
);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(with_sample=True):
    conn = get_db()
    conn.executescript(SCHEMA)
    if not conn.execute("SELECT 1 FROM admin").fetchone():
        conn.execute("INSERT INTO admin (username, password_hash) VALUES (?, ?)",
                     ("admin", generate_password_hash("admin123")))
    if with_sample and not conn.execute("SELECT 1 FROM students").fetchone():
        path = os.path.join(BASE_DIR, "sample_data", "sample_students.csv")
        if os.path.exists(path):
            with open(path, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    conn.execute(
                        "INSERT OR IGNORE INTO students (student_id,name,department,year,subject,register_no) VALUES (?,?,?,?,?,?)",
                        (r["student_id"], r["name"], r["department"], int(r["year"]), r["subject"], r["register_no"]))
        exams = [("Semester Exam", "Data Structures", "2026-12-01", "Morning"),
                 ("Semester Exam", "Digital Electronics", "2026-12-01", "Morning"),
                 ("Semester Exam", "Thermodynamics", "2026-12-01", "Morning"),
                 ("Semester Exam", "Engineering Mathematics", "2026-12-01", "Morning")]
        for e in exams:
            n = conn.execute("SELECT COUNT(*) FROM students WHERE subject=?", (e[1],)).fetchone()[0]
            conn.execute("INSERT INTO exams (name,subject,exam_date,session,num_students) VALUES (?,?,?,?,?)", (*e, n))
        for h in [("Hall A", "101", 6, 6), ("Hall B", "102", 6, 6), ("Hall C", "103", 5, 6)]:
            conn.execute("INSERT INTO examination_halls (hall_name,hall_number,rows,cols,capacity) VALUES (?,?,?,?,?)",
                         (*h, h[2] * h[3]))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialised at", DB_PATH)
    print("Default login -> username: admin  password: admin123")

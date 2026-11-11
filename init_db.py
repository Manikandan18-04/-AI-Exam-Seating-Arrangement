"""Run: python init_db.py  -> creates exam_seating.db with admin + sample data."""
from database import init_db, DB_PATH
init_db()
print("Database ready:", DB_PATH, "| login admin / admin123")

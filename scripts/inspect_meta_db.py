"""
Inspect tables, schemas, and row counts in data/meta.db
"""
import sqlite3
from pathlib import Path

def main():
    db_path = Path("data/meta.db")
    if not db_path.exists():
        print("data/meta.db does not exist!")
        return

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    tables = [t[0] for t in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables in meta.db:", tables)
    for t in tables:
        cnt = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        cols = [col[1] for col in c.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"\nTable: {t} ({cnt} rows)")
        print(f"  Columns: {cols}")
        if cnt > 0:
            sample = c.execute(f"SELECT * FROM {t} LIMIT 2").fetchall()
            print(f"  Sample row 0: {sample[0]}")
    conn.close()

if __name__ == "__main__":
    main()

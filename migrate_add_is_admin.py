#!/usr/bin/env python3
"""
One-off migration: add is_admin column to users table.
Run once on PythonAnywhere (Bash console):
  cd ~/stock_ms/max   # or your project path
  python migrate_add_is_admin.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stock.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cur.fetchall()]
    if 'is_admin' in columns:
        print("Column 'is_admin' already exists. Nothing to do.")
        conn.close()
        return
    cur.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    conn.commit()
    conn.close()
    print("Done: added column 'is_admin' to users.")

if __name__ == "__main__":
    migrate()

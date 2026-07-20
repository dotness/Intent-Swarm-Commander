import sqlite3
import json
import argparse
import sys
import os

DB_FILE = os.path.join(os.getcwd(), 'ltv_database.db')

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ltv_vision (
            id INTEGER PRIMARY KEY,
            as_is TEXT,
            to_be TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cone_paths (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            description TEXT,
            status TEXT,
            metadata JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS node_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            description TEXT,
            timestamp TEXT,
            metadata JSON
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS false_cones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            reason TEXT,
            metadata JSON
        )
    ''')

    conn.commit()
    conn.close()

def set_vision(as_is, to_be):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM ltv_vision')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO ltv_vision (id, as_is, to_be) VALUES (1, ?, ?)', (as_is, to_be))
    else:
        cursor.execute('UPDATE ltv_vision SET as_is = ?, to_be = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1', (as_is, to_be))

    conn.commit()
    conn.close()
    print("Vision updated successfully.")

def get_vision():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT as_is, to_be FROM ltv_vision WHERE id = 1')
    row = cursor.fetchone()
    conn.close()

    if row:
        print(f"AS-IS: {row[0]}\nTO-BE: {row[1]}")
    else:
        print("No vision set yet.")

def add_path(name, description, status, metadata=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    metadata_json = json.dumps(metadata) if metadata else '{}'
    try:
        cursor.execute('INSERT INTO cone_paths (name, description, status, metadata) VALUES (?, ?, ?, ?)',
                       (name, description, status, metadata_json))
        conn.commit()
        print(f"Path '{name}' added successfully.")
    except sqlite3.IntegrityError:
        print(f"Error: Path '{name}' already exists.")
    finally:
        conn.close()

def update_path_status(name, status):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE cone_paths SET status = ? WHERE name = ?', (status, name))

    if cursor.rowcount > 0:
        print(f"Path '{name}' status updated to '{status}'.")
    else:
        print(f"Error: Path '{name}' not found.")

    conn.commit()
    conn.close()

def get_all_paths():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT name, description, status, metadata FROM cone_paths')
    rows = cursor.fetchall()
    conn.close()

    if rows:
        for r in rows:
            print(f"- {r[0]} ({r[2]}): {r[1]} [Meta: {r[3]}]")
    else:
        print("No paths found.")

if __name__ == "__main__":
    init_db()

    parser = argparse.ArgumentParser(description="Manage LTV Cone")
    parser.add_argument("--action", required=True, choices=['set_vision', 'get_vision', 'add_path', 'update_path_status', 'get_all_paths'])
    parser.add_argument("--as_is", help="AS-IS state description")
    parser.add_argument("--to_be", help="TO-BE state description")
    parser.add_argument("--name", help="Name of the path")
    parser.add_argument("--description", help="Description of the path")
    parser.add_argument("--status", help="Status of the path (e.g., hypothetical, aligned, eliminated)")
    parser.add_argument("--metadata", help="JSON string of metadata")

    args = parser.parse_args()

    if args.action == "set_vision":
        if not args.as_is or not args.to_be:
            print("Error: --as_is and --to_be are required for set_vision")
            sys.exit(1)
        set_vision(args.as_is, args.to_be)
    elif args.action == "get_vision":
        get_vision()
    elif args.action == "add_path":
        if not args.name or not args.description or not args.status:
            print("Error: --name, --description, and --status are required for add_path")
            sys.exit(1)
        meta = json.loads(args.metadata) if args.metadata else None
        add_path(args.name, args.description, args.status, meta)
    elif args.action == "update_path_status":
        if not args.name or not args.status:
            print("Error: --name and --status are required for update_path_status")
            sys.exit(1)
        update_path_status(args.name, args.status)
    elif args.action == "get_all_paths":
        get_all_paths()

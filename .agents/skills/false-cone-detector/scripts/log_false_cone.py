import sqlite3
import json
import argparse
import sys
import os

DB_FILE = os.path.join(os.getcwd(), 'ltv_database.db')

def log_cone(name, reason, metadata=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    metadata_json = json.dumps(metadata) if metadata else '{}'
    try:
        cursor.execute('INSERT INTO false_cones (name, reason, metadata) VALUES (?, ?, ?)',
                       (name, reason, metadata_json))
        conn.commit()
        print(f"False Cone '{name}' logged successfully.")
    except sqlite3.IntegrityError:
        print(f"Error: False Cone '{name}' already exists.")
    finally:
        conn.close()

def get_cones():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT name, reason, metadata FROM false_cones')
    rows = cursor.fetchall()
    conn.close()

    if rows:
        for r in rows:
            print(f"- {r[0]} (Reason: {r[1]}) [Meta: {r[2]}]")
    else:
        print("No False Cones logged.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Log False Cones")
    parser.add_argument("--action", required=True, choices=['log_cone', 'get_cones'])
    parser.add_argument("--name", help="Name of the false trend/cone")
    parser.add_argument("--reason", help="Reason for rejection")
    parser.add_argument("--metadata", help="JSON string of metadata")

    args = parser.parse_args()

    if args.action == "log_cone":
        if not args.name or not args.reason:
            print("Error: --name and --reason are required for log_cone")
            sys.exit(1)
        meta = json.loads(args.metadata) if args.metadata else None
        log_cone(args.name, args.reason, meta)
    elif args.action == "get_cones":
        get_cones()

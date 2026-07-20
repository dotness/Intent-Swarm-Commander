import sqlite3
import json
import argparse
import sys
import os

DB_FILE = os.path.join(os.getcwd(), 'ltv_database.db')

def add_node(name, description, timestamp, metadata=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    metadata_json = json.dumps(metadata) if metadata else '{}'
    try:
        cursor.execute('INSERT INTO node_points (name, description, timestamp, metadata) VALUES (?, ?, ?, ?)',
                       (name, description, timestamp, metadata_json))
        conn.commit()
        print(f"Node Point '{name}' added successfully.")
    except sqlite3.IntegrityError:
        print(f"Error: Node Point '{name}' already exists.")
    finally:
        conn.close()

def get_nodes():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT name, description, timestamp, metadata FROM node_points')
    rows = cursor.fetchall()
    conn.close()

    if rows:
        for r in rows:
            print(f"- {r[0]} (Time: {r[2]}): {r[1]} [Meta: {r[3]}]")
    else:
        print("No Node Points found.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage Node Points")
    parser.add_argument("--action", required=True, choices=['add_node', 'get_nodes'])
    parser.add_argument("--name", help="Name of the node point")
    parser.add_argument("--description", help="Description")
    parser.add_argument("--timestamp", help="Time or stage of the node")
    parser.add_argument("--metadata", help="JSON string of metadata")

    args = parser.parse_args()

    if args.action == "add_node":
        if not args.name or not args.description or not args.timestamp:
            print("Error: --name, --description, and --timestamp are required for add_node")
            sys.exit(1)
        meta = json.loads(args.metadata) if args.metadata else None
        add_node(args.name, args.description, args.timestamp, meta)
    elif args.action == "get_nodes":
        get_nodes()

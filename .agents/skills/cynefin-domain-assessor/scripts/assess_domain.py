import argparse
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'cynefin.db')
VALID_DOMAINS = ["Clear", "Complicated", "Complex", "Chaotic"]

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            domain TEXT NOT NULL,
            reason TEXT NOT NULL,
            metadata TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def log_assessment(name, domain, reason, metadata=None):
    if domain not in VALID_DOMAINS:
        print(f"Error: Domain must be one of {VALID_DOMAINS}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    meta_json = json.dumps(metadata) if metadata else None

    cursor.execute('''
        INSERT INTO assessments (name, domain, reason, metadata)
        VALUES (?, ?, ?, ?)
    ''', (name, domain, reason, meta_json))

    conn.commit()
    print(f"Logged Cynefin assessment: '{name}' classified as '{domain}'.")
    conn.close()

def get_assessments():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT name, domain, reason, metadata, timestamp FROM assessments ORDER BY timestamp DESC')
    assessments = cursor.fetchall()

    if not assessments:
        print("No Cynefin assessments logged yet.")
    else:
        print("--- Cynefin Domain Assessments ---")
        for a in assessments:
            print(f"[{a[4]}] {a[0]}")
            print(f"  Domain: {a[1]}")
            print(f"  Reason: {a[2]}")
            if a[3]:
                print(f"  Metadata: {a[3]}")
            print("-" * 20)

    conn.close()

def main():
    parser = argparse.ArgumentParser(description="Cynefin Domain Assessor Script")
    parser.add_argument('--action', choices=['log_assessment', 'get_assessments'], required=True)
    parser.add_argument('--name', type=str, help="Name of the architectural challenge or market signal")
    parser.add_argument('--domain', type=str, choices=VALID_DOMAINS, help="Cynefin domain classification")
    parser.add_argument('--reason', type=str, help="Justification for the classification")
    parser.add_argument('--metadata', type=str, help="Optional metadata in JSON format")

    args = parser.parse_args()

    init_db()

    if args.action == 'log_assessment':
        if not args.name or not args.domain or not args.reason:
            print("Error: --name, --domain, and --reason are required for log_assessment.")
            return

        metadata_dict = None
        if args.metadata:
            try:
                metadata_dict = json.loads(args.metadata)
            except json.JSONDecodeError:
                print("Error: --metadata must be valid JSON.")
                return

        log_assessment(args.name, args.domain, args.reason, metadata_dict)

    elif args.action == 'get_assessments':
        get_assessments()

if __name__ == "__main__":
    main()

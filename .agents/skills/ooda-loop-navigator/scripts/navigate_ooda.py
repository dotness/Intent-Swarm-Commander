import argparse
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'ooda.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ooda_loops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_node TEXT NOT NULL,
            observation TEXT NOT NULL,
            orientation_analysis TEXT,
            anomaly_detected BOOLEAN,
            decision_hypothesis TEXT,
            action_plan TEXT,
            action_outcome TEXT,
            status TEXT DEFAULT 'Observing',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def log_observation(target_node, observation):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO ooda_loops (target_node, observation)
        VALUES (?, ?)
    ''', (target_node, observation))
    loop_id = cursor.lastrowid
    conn.commit()
    print(f"Logged new OODA loop (ID: {loop_id}) observation for Node Point: '{target_node}'.")
    conn.close()

def log_orientation(observation_id, analysis, anomaly_detected):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE ooda_loops
        SET orientation_analysis = ?, anomaly_detected = ?, status = 'Oriented', updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (analysis, anomaly_detected, observation_id))

    if cursor.rowcount == 0:
        print(f"Error: OODA loop with ID {observation_id} not found.")
    else:
        print(f"Logged orientation for OODA loop ID: {observation_id}.")
        if anomaly_detected:
            print("WARNING: Anomaly detected! Flagged for architectural review.")

    conn.commit()
    conn.close()

def log_decision(observation_id, hypothesis, action_plan):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE ooda_loops
        SET decision_hypothesis = ?, action_plan = ?, status = 'Decided', updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (hypothesis, action_plan, observation_id))

    if cursor.rowcount == 0:
        print(f"Error: OODA loop with ID {observation_id} not found.")
    else:
        print(f"Logged decision for OODA loop ID: {observation_id}.")

    conn.commit()
    conn.close()

def log_action(observation_id, outcome):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE ooda_loops
        SET action_outcome = ?, status = 'Completed', updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (outcome, observation_id))

    if cursor.rowcount == 0:
        print(f"Error: OODA loop with ID {observation_id} not found.")
    else:
        print(f"Logged action outcome for OODA loop ID: {observation_id}. Loop is now Completed.")

    conn.commit()
    conn.close()

def get_loops(target_node=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if target_node:
        cursor.execute('SELECT * FROM ooda_loops WHERE target_node = ? ORDER BY updated_at DESC', (target_node,))
    else:
        cursor.execute('SELECT * FROM ooda_loops ORDER BY updated_at DESC')

    loops = cursor.fetchall()

    if not loops:
        print("No OODA loops found.")
    else:
        print("--- OODA Loops ---")
        for loop in loops:
            print(f"Loop ID: {loop[0]} | Status: {loop[8]} | Target Node: {loop[1]}")
            print(f"  Observed: {loop[2]}")
            if loop[3]: print(f"  Oriented: {loop[3]} (Anomaly: {bool(loop[4])})")
            if loop[5]: print(f"  Decided: {loop[5]} | Plan: {loop[6]}")
            if loop[7]: print(f"  Action Outcome: {loop[7]}")
            print("-" * 20)

    conn.close()

def main():
    parser = argparse.ArgumentParser(description="OODA Loop Navigator Script")
    parser.add_argument('--action', choices=['log_observation', 'log_orientation', 'log_decision', 'log_action', 'get_loops'], required=True)
    parser.add_argument('--target_node', type=str, help="Target Node Point in the Cone")
    parser.add_argument('--observation', type=str, help="Telemetry or market data")
    parser.add_argument('--observation_id', type=int, help="ID of the OODA loop")
    parser.add_argument('--analysis', type=str, help="Contextualization of the observation")

    # We parse boolean nicely by checking string value
    parser.add_argument('--anomaly_detected', type=str, choices=['True', 'False'], help="Is the observation an anomaly?")

    parser.add_argument('--hypothesis', type=str, help="Micro-hypothesis for the next step")
    parser.add_argument('--action_plan', type=str, help="Actionable plan to test hypothesis")
    parser.add_argument('--outcome', type=str, help="Result of the action")

    args = parser.parse_args()

    init_db()

    if args.action == 'log_observation':
        if not args.target_node or not args.observation:
            print("Error: --target_node and --observation are required.")
            return
        log_observation(args.target_node, args.observation)

    elif args.action == 'log_orientation':
        if not args.observation_id or not args.analysis or not args.anomaly_detected:
            print("Error: --observation_id, --analysis, and --anomaly_detected are required.")
            return
        anomaly = True if args.anomaly_detected == 'True' else False
        log_orientation(args.observation_id, args.analysis, anomaly)

    elif args.action == 'log_decision':
        if not args.observation_id or not args.hypothesis or not args.action_plan:
            print("Error: --observation_id, --hypothesis, and --action_plan are required.")
            return
        log_decision(args.observation_id, args.hypothesis, args.action_plan)

    elif args.action == 'log_action':
        if not args.observation_id or not args.outcome:
            print("Error: --observation_id and --outcome are required.")
            return
        log_action(args.observation_id, args.outcome)

    elif args.action == 'get_loops':
        get_loops(args.target_node)

if __name__ == "__main__":
    main()

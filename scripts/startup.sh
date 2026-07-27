#!/usr/bin/env bash
# Startup script for Intent-Swarm-Commander MVP

set -e

echo "Starting Intent Swarm Commander..."

cd "$(dirname "$0")/../src/docker"

# Spin up Postgres and Temporal first
echo "Bringing up infrastructure..."
docker compose up -d postgres temporal temporal-ui

echo "Waiting for Temporal to be ready..."
sleep 15

# Start the API
echo "Starting ISC Backend..."
docker compose up -d isc-api

echo "Intent Swarm Commander is running."
echo "API: http://localhost:8000"
echo "Temporal UI: http://localhost:8080"
echo "To view dashboard, open src/dashboard/index.html in your browser."

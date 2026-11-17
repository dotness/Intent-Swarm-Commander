# Implementation Plan: Multi-Drone Vision Streams, Web GUI Snapshots & Detection HITL

**Branch**: `010-multi-drone-vision-hitl` | **Date**: 2026-11-17 | **Spec**: [spec.md](file:///home/remi/Projects/Intent-Swarm-Commander/specs/010-multi-drone-vision-hitl/spec.md)  
**Input**: Feature specification from `/specs/010-multi-drone-vision-hitl/spec.md`

## Summary

Enable independent per-drone video feeding and streaming (`POST /feed/{drone_id}` and `GET /stream/{drone_id}`), per-drone vision detection channels on `isc_edge` (sharing `YoloEInference` in local simulation while keeping 1:1 `DRONE_ID`/`CAMERA_SOURCE` compatibility for Raspberry Pi 5), a **Drone Vision & Snapshots** Web GUI panel to watch live feeds and per-drone JPEG crops, and in-flight detection HITL decisions (`HitlDecision`) rendering the captured JPEG snapshot inside `#hitl-modal`.

## Technical Context

**Language/Version**: Python 3.10+ (containers) / 3.14 (host `.venv`), Vanilla JS/HTML (Dashboard), Playwright E2E  
**Primary Dependencies**: FastAPI, OpenCV, Ultralytics (`yolov8n.pt`), SQLAlchemy Async, MinIO (`boto3`), Memgraph, Mosquitto MQTT  
**Storage**: PostgreSQL (`hitl_decisions`, `swarm_live_states`), MinIO (`tactical-snapshots`), Memgraph  
**Testing**: `pytest` (unit/contract/integration), Playwright (`tests/e2e/`)  
**Constraints**: Constitution Principles V–VII (scripts in `scripts/`, zero mocks in `src/`, single canonical paths, unconditional imports).

## Constitution Check

- **V (Script Organization)**: `virtual_cam_server.py` stays in `scripts/`.
- **VI & VII (Purity & Single-Path)**: Zero mock frames/detections in `src/`, unconditional imports, strict regex validation on `drone_id`, idempotent schema columns via SQLAlchemy/DDL.

## Project Structure

```text
scripts/virtual_cam_server.py                  # Multi-drone /stream/{drone_id} & /feed/{drone_id}
docker-compose.yml                             # Expose VIRTUAL_CAM_BASE_URL to edge_drone
src/edge/telemetry/publisher.py                # Optional drone_id override on publish_detection
src/edge/api/server.py                         # Per-drone _vision_tasks / CameraStream + drone_id on /target
src/uservice/database/engine.py                # Idempotent ALTER TABLE for new hitl_decisions columns
src/uservice/hitl/models/storage/decision.py   # Optional detection metadata columns on HitlDecision
src/uservice/hitl/models/contract/schemas.py   # Detection metadata fields on HitlPendingItem
src/uservice/hitl/facade/hitl.py               # Accept/return detection metadata on create & pending
src/uservice/main.py                           # Create pending HitlDecision on intercept/hitl detection
src/dashboard/index.html                       # Drone Vision & Snapshots panel
src/dashboard/js/main.js                       # Per-drone stream switcher & snapshot gallery
src/dashboard/js/hitl.js                       # Render drone_id + detection JPEG snapshot in #hitl-modal
tests/e2e/multi_drone_vision_hitl.spec.js      # Zero-mock E2E verifying 5-drone /feed, /stream, GUI & HITL snapshots
```

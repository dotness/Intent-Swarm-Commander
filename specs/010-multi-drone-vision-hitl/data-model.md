# Data Model: Multi-Drone Vision, Web GUI Snapshots & Detection HITL (`010-multi-drone-vision-hitl`)

## 1. Virtual Camera Endpoints (`isc_virtual_cam:8091`)
- `GET /stream/{drone_id}` (`drone_id` matching `^[a-zA-Z0-9_-]{1,64}$`; `/stream` aliases `"drone-1"`)
- `POST /feed/{drone_id}` (`{"mode": "clear" | "target", "path"?: string}`; `/feed` aliases `"drone-1"`)
- `GET /feed/{drone_id}` (returns `{drone_id, mode, media_path, version}`; `/feed` returns `"drone-1"` + all channels)

## 2. Edge `/target` Request (`src/edge/api/server.py`)
- `TargetRequest`:
  - `target_object_class: str`
  - `command_id: str`
  - `confidence_threshold: float = 0.5`
  - `detection_mode: Literal["report_only", "intercept"] = "report_only"`
  - `drone_id: str | None = None` (defaults to `os.getenv("DRONE_ID", "drone-1")`)

## 3. `HitlDecision` & `HitlPendingItem` Additions
- `drone_id: str | None`
- `detection_event_id: str | None`
- `snapshot_url: str | None` (`/api/v1/analytics/detections/{event_id}/snapshot?project_id=...`)
- `target_class: str | None`
- `confidence: float | None`

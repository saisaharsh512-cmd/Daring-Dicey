"""
api/server.py

MINIMUM NECESSARY ADDITION for the demo frontend. This file does not touch
model logic, severity scoring, routing, or aggregation in any way -- it is a
thin HTTP wrapper around the existing `analyze_disaster()` entry point in
api/backend.py, which previously was only callable as a Python function.

What this adds:
  - A single POST /api/analyze endpoint that accepts multipart/form-data
    (disaster_type + one or more images + one JSON-encoded locations array),
    writes the uploaded images to a temp directory, calls the EXISTING
    analyze_disaster() unchanged, and returns its result as JSON.
  - CORS, so a browser-based frontend on a different port (Vite's :5173)
    can call this API.
  - A GET /api/health check and GET /api/disaster-types passthrough so the
    frontend can populate its dropdown from the backend's own routing table
    instead of hardcoding disaster types on the frontend.

Nothing here recomputes severity, invents damage categories, or duplicates
model logic. All of that continues to happen exclusively inside
analyze_disaster() and the modules it calls.

Run with:
    uvicorn api.server:app --reload --port 8000
(from the backend/ directory, same as any other backend command)
"""
import logging
import re
import shutil
import tempfile
import uuid
import json
from pathlib import Path
from typing import List

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.backend import analyze_disaster
from aggregation.location_aggregator import DEFAULT_CLUSTER_TOLERANCE_METERS
from inference.disaster_router import VALID_DISASTER_TYPES
from scoring.disaster_weights import get_route
from scoring.evacuation_route import calculate_road_route

log = logging.getLogger("backend.api.server")

app = FastAPI(title="Disaster Assessment API", version="1.0.0")

# Demo-only CORS: the Vite dev server runs on a different origin than this
# API. Wide open for hackathon convenience -- tighten before any real
# deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]")


def _cleanup(path: Path):
    shutil.rmtree(path, ignore_errors=True)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/disaster-types")
def disaster_types():
    """
    Lets the frontend build its disaster-type dropdown from the backend's
    own routing table, rather than hardcoding a list that could drift out
    of sync with scoring/disaster_weights.py.
    """
    types = sorted(VALID_DISASTER_TYPES)
    return {
        "disaster_types": [
            {"value": t, "models_run": get_route(t)["run"]} for t in types
        ]
    }




@app.post("/api/evacuation-route")
async def evacuation_route(payload: dict):
    """Calculate a road-network route from an affected location to a user-selected safe zone."""
    required = ("origin_latitude", "origin_longitude", "destination_latitude", "destination_longitude")
    missing = [key for key in required if key not in payload]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing route fields: {', '.join(missing)}")

    try:
        route = calculate_road_route(
            payload["origin_latitude"],
            payload["origin_longitude"],
            payload["destination_latitude"],
            payload["destination_longitude"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        log.exception("[API] evacuation route calculation failed")
        raise HTTPException(status_code=502, detail=f"Could not calculate an evacuation route: {exc}")

    return {
        "success": True,
        "origin": {
            "latitude": float(payload["origin_latitude"]),
            "longitude": float(payload["origin_longitude"]),
        },
        "destination": {
            "latitude": float(payload["destination_latitude"]),
            "longitude": float(payload["destination_longitude"]),
            "name": str(payload.get("destination_name") or "Safe Zone"),
        },
        **route,
    }

@app.post("/api/analyze")
async def analyze(
    background_tasks: BackgroundTasks,
    disaster_type: str = Form(...),
    locations: str = Form(...),
    cluster_tolerance_meters: float = Form(DEFAULT_CLUSTER_TOLERANCE_METERS),
    total_rescue_members: int = Form(0),
    images: List[UploadFile] = File(...),
):
    """
    multipart/form-data:
      disaster_type: str, e.g. "earthquake"
      locations: JSON array string, same length/order as `images`, e.g.
                 '[{"latitude": 12.9716, "longitude": 77.5946}, ...]'
                 An entry may be null if that image's location was invalid --
                 the existing backend's own validate_location() will then
                 correctly reject just that image into `skipped_images`.
      cluster_tolerance_meters: optional float, defaults to backend's own default
      images: one or more image files, order-aligned with `locations`

    Returns the EXACT structured result of analyze_disaster(), unmodified,
    plus one extra top-level field ("image_id_map") added by this wrapper
    only, so the frontend can match detected_damage[].source_image back to
    the browser-side file it originally uploaded (the backend evidence
    schema itself is untouched).
    """
    try:
        parsed_locations = json.loads(locations)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="`locations` must be a valid JSON array")

    if not isinstance(parsed_locations, list):
        raise HTTPException(status_code=400, detail="`locations` must be a JSON array")

    if len(parsed_locations) != len(images):
        raise HTTPException(
            status_code=400,
            detail=f"locations count ({len(parsed_locations)}) must match images count ({len(images)})",
        )

    if len(images) == 0:
        raise HTTPException(status_code=400, detail="no images provided")

    tmp_dir = Path(tempfile.mkdtemp(prefix="disaster_analyze_"))
    background_tasks.add_task(_cleanup, tmp_dir)

    backend_images = []
    image_id_map = {}  # server-side filename actually passed to the backend -> original browser filename

    for i, (upload, loc) in enumerate(zip(images, parsed_locations)):
        original_name = upload.filename or f"image_{i}"
        ext = Path(original_name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            ext = ".jpg"  # backend's own validate_image() will reject this file cleanly with a clear error either way

        safe_stub = SAFE_NAME_RE.sub("_", Path(original_name).stem)[:40] or "image"
        server_name = f"img_{i}_{safe_stub}{ext}"
        dest = tmp_dir / server_name

        content = await upload.read()
        dest.write_bytes(content)

        image_id_map[server_name] = original_name

        entry = {"image_path": str(dest)}
        if loc is not None:
            entry["location"] = {
                "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"),
            }
        # if loc is None, no location keys are set at all -- the existing
        # validate_location() in inference_engine.py already handles that
        # by cleanly skipping the image with "missing latitude/longitude"
        backend_images.append(entry)

    try:
        result = analyze_disaster(
            disaster_type=disaster_type,
            images=backend_images,
            cluster_tolerance_meters=cluster_tolerance_meters,
            total_rescue_members=total_rescue_members,
        )
    except Exception as e:
        log.exception("[API] analyze_disaster crashed")
        raise HTTPException(status_code=500, detail=f"analysis failed: {e}")

    result["image_id_map"] = image_id_map
    return JSONResponse(content=result)

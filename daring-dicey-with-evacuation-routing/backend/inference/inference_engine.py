"""
inference/inference_engine.py

Validates one image+location input and runs every routed model on it,
producing standardized per-model outputs plus a flattened list of
severity-scored evidence ready for location aggregation.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List

from PIL import Image, UnidentifiedImageError

from inference.model_manager import run_model
from inference.disaster_router import route
from scoring.severity_engine import compute_detection_severity_value
from scoring.relevance_gate import general_disaster_gate, disaster_type_gate

log = logging.getLogger("backend.inference_engine")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def validate_image(image_path: str) -> Dict[str, Any]:
    """Returns {'valid': bool, 'error': str|None}. Never raises."""
    path = Path(image_path)
    if not path.exists():
        return {"valid": False, "error": f"image not found: {image_path}"}
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        return {"valid": False, "error": f"unsupported file type '{path.suffix}' (allowed: {sorted(ALLOWED_EXTENSIONS)})"}
    try:
        img = Image.open(path)
        img.verify()
    except (UnidentifiedImageError, OSError) as e:
        return {"valid": False, "error": f"corrupt or unreadable image: {e}"}
    return {"valid": True, "error": None}


def validate_location(image_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Returns {'valid': bool, 'error': str|None}."""
    loc = image_entry.get("location")
    if loc is None:
        lat, lng = image_entry.get("latitude"), image_entry.get("longitude")
    else:
        lat, lng = loc.get("latitude"), loc.get("longitude")
    if lat is None or lng is None:
        return {"valid": False, "error": "missing latitude/longitude"}
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return {"valid": False, "error": f"non-numeric coordinates: {lat!r}, {lng!r}"}
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return {"valid": False, "error": f"coordinates out of range: {lat}, {lng}"}
    return {"valid": True, "error": None, "latitude": lat, "longitude": lng}


def analyze_image(image_path: str, disaster_type: str) -> Dict[str, Any]:
    """
    THE gate-enforced pipeline for one image:
      1. general disaster relevance gate
      2. selected-disaster-type relevance gate (skipped entirely for "other")
      3. only if BOTH pass RELEVANT: run the routed specialized models

    Returns:
      {'image_path', 'gate_status', 'general_gate', 'type_gate',
       'models_run', 'models_skipped_by_router', 'models_skipped_by_gate',
       'model_outputs', 'evidence'}

    A model_outputs entry only exists for models that actually ran --
    models skipped by the gate are listed in 'models_skipped_by_gate',
    never given a fake result.
    """
    routing = route(disaster_type)

    general_gate = general_disaster_gate(image_path)
    type_gate = disaster_type_gate(image_path, disaster_type)

    general_ok = general_gate["state"] == "RELEVANT"
    type_ok = (type_gate is None) or (type_gate["state"] == "RELEVANT")
    gate_passed = general_ok and type_ok

    if not general_ok:
        gate_status = "NOT_A_DISASTER" if general_gate["state"] == "NOT_RELEVANT" else "UNCERTAIN_NOT_A_DISASTER"
    elif not type_ok:
        gate_status = "NOT_RELEVANT_TO_SELECTED_TYPE" if type_gate["state"] == "NOT_RELEVANT" else "UNCERTAIN_TYPE_RELEVANCE"
    else:
        gate_status = "DISASTER_DETECTED"

    model_outputs = {}
    evidence: List[Dict[str, Any]] = []

    if gate_passed:
        for model_name in routing["run"]:
            output = run_model(model_name, image_path)
            model_outputs[model_name] = output

            if output.get("error"):
                log.warning("[MODEL] %s failed on %s: %s", model_name, image_path, output["error"])
                continue

            for det in output.get("detections", []):
                severity_value = compute_detection_severity_value(model_name, det["damage_type"], det["confidence"])
                evidence.append({
                    "model": model_name,
                    "damage_type": det["damage_type"],
                    "confidence": det["confidence"],
                    "bbox": det["bbox"],
                    "evidence_type": det["evidence_type"],
                    "severity_value": severity_value,
                    "image_path": image_path,
                })
    else:
        log.info("[GATE] %s -- specialized models NOT run for %s (RULE 1/2 enforcement)",
                  gate_status, image_path)

    return {
        "image_path": image_path,
        "disaster_recognized": routing["recognized"],
        "gate_status": gate_status,
        "gate_passed": gate_passed,
        "general_gate": general_gate,
        "type_gate": type_gate,
        "models_run": routing["run"] if gate_passed else [],
        "models_skipped_by_router": routing["skip"],
        "models_skipped_by_gate": [] if gate_passed else routing["run"],
        "model_outputs": model_outputs,
        "evidence": evidence,
    }

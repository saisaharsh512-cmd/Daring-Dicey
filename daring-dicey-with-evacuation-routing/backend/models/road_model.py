"""
models/road_model.py

Wraps nsr51324/Road_Damage_Object_Detection (YOLOv8n, real object detector,
local .pt via huggingface_hub). Verified against the model's own confusion
matrix -- classes below are confirmed, not assumed.

Classes: alligator, block, crack, edge, longitudinal, pothole, transverse.
NOTE: there is no "Repair" class in this checkpoint -- it cannot detect
repaired road areas. That is a real capability gap, not a bug here.
"""
import logging
from pathlib import Path
from functools import lru_cache

from huggingface_hub import hf_hub_download
from ultralytics import YOLO

from schemas.output_schema import make_detection, make_model_output

log = logging.getLogger("backend.road_model")

REPO_ID = "nsr51324/Road_Damage_Object_Detection"
WEIGHTS_FILENAME = "runs/detect/yolov8_road/weights/best.pt"

# Human-readable labels, keyed by the model's real (lowercased) class strings.
DAMAGE_LABELS = {
    "longitudinal": "Longitudinal Crack",
    "transverse": "Transverse Crack",
    "alligator": "Alligator Crack",
    "pothole": "Pothole",
    "block": "Block Crack",
    "crack": "Unspecified Crack",
    "edge": "Edge Crack",
}


@lru_cache(maxsize=1)
def _load_model():
    log.info("[MODEL] Loading road model...")
    weights_path = hf_hub_download(repo_id=REPO_ID, filename=WEIGHTS_FILENAME)
    model = YOLO(weights_path)
    log.info("[MODEL] Road model loaded (classes: %s)", model.names)
    return model


def analyze(image_path: str, conf_threshold: float = 0.25) -> dict:
    """Runs road damage detection on one image. Never raises -- failures come back as error field."""
    try:
        model = _load_model()
    except Exception as e:
        return make_model_output("road", "object_detection", [], error=f"model load failed: {e}")

    try:
        results = model.predict(source=image_path, conf=conf_threshold, verbose=False)
    except Exception as e:
        return make_model_output("road", "object_detection", [], error=f"inference failed: {e}")

    detections = []
    boxes = results[0].boxes
    if boxes is not None:
        for box in boxes:
            cls_id = int(box.cls.item())
            confidence = float(box.conf.item())
            raw_class = model.names.get(cls_id, f"class_{cls_id}")
            human_label = DAMAGE_LABELS.get(raw_class.lower(), raw_class)
            xyxy = box.xyxy[0].tolist()
            detections.append(make_detection(human_label, confidence, bbox=xyxy, raw_class=raw_class))

    log.info("[DETECTION] road: %d damage regions detected", len(detections))
    return make_model_output("road", "object_detection", detections)

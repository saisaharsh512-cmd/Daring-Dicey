"""
models/fire_model.py

Wraps rabahdev/fire-smoke-yolov8n (YOLOv8n, real object detector, local .pt
via huggingface_hub). Verified real & working in your firemodel.ipynb
(9 detections on your test image, confidences 0.27-0.67).

Classes confirmed from your notebook's own output: {0: 'smoke', 1: 'fire'}

FIX APPLIED (documented per your "fix bugs, preserve architecture" allowance):
your original notebook's fire_assessment() bucketed severity directly off
max confidence (>=0.70 -> CRITICAL, etc), which conflates confidence with
severity -- exactly what you asked this backend to avoid. This wrapper only
extracts raw detections; severity is computed centrally in scoring/severity_engine.py
using the damage-type-aware formula, consistent with every other model.
"""
import logging
from functools import lru_cache

from huggingface_hub import hf_hub_download
from ultralytics import YOLO

from schemas.output_schema import make_detection, make_model_output

log = logging.getLogger("backend.fire_model")

REPO_ID = "rabahdev/fire-smoke-yolov8n"
WEIGHTS_FILENAME = "best.pt"

DAMAGE_LABELS = {"fire": "Fire", "smoke": "Smoke"}


@lru_cache(maxsize=1)
def _load_model():
    log.info("[MODEL] Loading fire/smoke model...")
    weights_path = hf_hub_download(repo_id=REPO_ID, filename=WEIGHTS_FILENAME)
    model = YOLO(weights_path)
    log.info("[MODEL] Fire/smoke model loaded (classes: %s)", model.names)
    return model


def analyze(image_path: str, conf_threshold: float = 0.25) -> dict:
    try:
        model = _load_model()
    except Exception as e:
        return make_model_output("fire", "object_detection", [], error=f"model load failed: {e}")

    try:
        results = model.predict(source=image_path, conf=conf_threshold, verbose=False)
    except Exception as e:
        return make_model_output("fire", "object_detection", [], error=f"inference failed: {e}")

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

    log.info("[DETECTION] fire: %d fire/smoke regions detected", len(detections))
    return make_model_output("fire", "object_detection", detections)

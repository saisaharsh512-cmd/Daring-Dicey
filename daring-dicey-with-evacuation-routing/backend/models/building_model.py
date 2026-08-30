"""
models/building_model.py

Wraps dolphinium/damaged-building-detection (YOLOv10 detection variant,
local .pt via huggingface_hub) -- verified real & working in your own
buildingmodel.ipynb (5 detections, confidences 0.28-0.76 on your test image).

Classes confirmed from your notebook's own output:
  {0: 'undamaged building', 1: 'damaged building'}

IMPORTANT, honestly stated: this is a BINARY detector. It has no gradation
between minor/moderate/severe/collapse -- only "damaged" vs "undamaged".
Only "damaged building" detections are reported here (undamaged buildings
are not damage evidence, so they're filtered out, matching how your own
notebook already only scored the damaged class).
"""
import logging
from functools import lru_cache

from huggingface_hub import hf_hub_download
from ultralytics import YOLO

from schemas.output_schema import make_detection, make_model_output

log = logging.getLogger("backend.building_model")

REPO_ID = "dolphinium/damaged-building-detection"
WEIGHTS_FILENAME = "rescuenet_yolo_runs/yolov10/yolov10m_bs_16_e100_full/weights/yolov10m-e100-b16-full-best.pt"

DAMAGE_CLASS_NAME = "damaged building"
HUMAN_LABEL = "Damaged Building"


@lru_cache(maxsize=1)
def _load_model():
    log.info("[MODEL] Loading building model...")
    weights_path = hf_hub_download(repo_id=REPO_ID, filename=WEIGHTS_FILENAME)
    model = YOLO(weights_path)
    log.info("[MODEL] Building model loaded (classes: %s)", model.names)
    return model


def analyze(image_path: str, conf_threshold: float = 0.25) -> dict:
    try:
        model = _load_model()
    except Exception as e:
        return make_model_output("building", "object_detection", [], error=f"model load failed: {e}")

    try:
        results = model.predict(source=image_path, conf=conf_threshold, verbose=False)
    except Exception as e:
        return make_model_output("building", "object_detection", [], error=f"inference failed: {e}")

    detections = []
    boxes = results[0].boxes
    if boxes is not None:
        for box in boxes:
            cls_id = int(box.cls.item())
            raw_class = model.names.get(cls_id, f"class_{cls_id}")
            if raw_class.strip().lower() != DAMAGE_CLASS_NAME:
                continue  # skip "undamaged building" -- not damage evidence
            confidence = float(box.conf.item())
            xyxy = box.xyxy[0].tolist()
            detections.append(make_detection(HUMAN_LABEL, confidence, bbox=xyxy, raw_class=raw_class))

    log.info("[DETECTION] building: %d damaged buildings detected", len(detections))
    return make_model_output(
        "building", "object_detection", detections,
        notes="Binary detector (damaged/undamaged only) -- no severity gradation classes available.",
    )

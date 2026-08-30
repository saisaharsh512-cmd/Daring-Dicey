"""
models/debris_model.py

REPLACES the previous remote inference-sdk/Roboflow implementation entirely.
inference-sdk is no longer a dependency anywhere in this project.

Local model: reuses dolphinium/damaged-building-detection's YOLOv8
SEGMENTATION checkpoint (rescuenet_yolo_runs/yolov8_seg/segment/weights/best.pt)
-- the same verified, already-trusted HF repo already used by building_model.py,
just a different weights file within it. Confirmed to exist (6.8MB, lfs) via
live Hugging Face Hub inspection before writing this file.

HONESTY NOTE on class discovery: RescueNet's published dataset taxonomy
(Rahnemoonfar et al.) documents a "Debris" segmentation class, but I could not
independently verify this specific checkpoint's exact class list without
downloading weights (no such access in the environment that wrote this file).
So this wrapper does NOT hardcode trust in that taxonomy -- it reads the
loaded model's REAL model.names at runtime and only reports debris evidence
if a class name actually matching debris/rubble semantics exists in THIS
checkpoint. If no such class exists, available=True (the model loaded fine)
but detections=[] with a clear note explaining why, rather than fabricating
a debris detection from an unrelated class.

This is a YOLOv8-seg model -- it produces both bounding boxes AND
segmentation masks. detection_type is reported as "segmentation" (not
"object_detection") so nothing downstream claims more precision than a
bounding box would represent while actually holding mask data, or vice
versa -- see RULE 8 (don't claim segmentation when only boxes exist, and
the reverse: don't hide that masks ARE available here).
"""
import logging
from functools import lru_cache

from huggingface_hub import hf_hub_download
from ultralytics import YOLO

from schemas.output_schema import make_detection, make_model_output

log = logging.getLogger("backend.debris_model")

REPO_ID = "dolphinium/damaged-building-detection"
WEIGHTS_FILENAME = "rescuenet_yolo_runs/yolov8_seg/segment/weights/best.pt"

DEBRIS_KEYWORDS = ("debris", "rubble")


@lru_cache(maxsize=1)
def _load_model():
    log.info("[MODEL] Loading debris model (local RescueNet YOLOv8-seg checkpoint)...")
    weights_path = hf_hub_download(repo_id=REPO_ID, filename=WEIGHTS_FILENAME)
    model = YOLO(weights_path)
    log.info("[MODEL] Debris model loaded (classes: %s)", model.names)
    return model


def _find_debris_class_ids(model) -> dict:
    """Returns {class_id: class_name} for any class whose name matches debris/rubble semantics."""
    return {
        cid: name for cid, name in model.names.items()
        if any(kw in name.lower() for kw in DEBRIS_KEYWORDS)
    }


def analyze(image_path: str, conf_threshold: float = 0.25) -> dict:
    try:
        model = _load_model()
    except Exception as e:
        return make_model_output(
            "debris", "segmentation", [], error=f"model load failed: {e}", available=False,
        )

    debris_class_ids = _find_debris_class_ids(model)
    if not debris_class_ids:
        return make_model_output(
            "debris", "segmentation", [], available=True,
            notes=(
                f"Model loaded successfully but its classes ({list(model.names.values())}) "
                f"contain no debris/rubble-labeled class -- no debris evidence can be reported "
                f"from this checkpoint. Not an error; a genuine scope limitation of this model."
            ),
        )

    try:
        results = model.predict(source=image_path, conf=conf_threshold, verbose=False)
    except Exception as e:
        return make_model_output("debris", "segmentation", [], error=f"inference failed: {e}", available=True)

    detections = []
    boxes = results[0].boxes
    if boxes is not None:
        for box in boxes:
            cls_id = int(box.cls.item())
            if cls_id not in debris_class_ids:
                continue  # only debris-labeled classes count as debris evidence -- other RescueNet
                          # classes this checkpoint might also detect are not this model's job to report
            confidence = float(box.conf.item())
            xyxy = box.xyxy[0].tolist()
            detections.append(make_detection(
                "Debris", confidence, bbox=xyxy, evidence_type="detection",
                raw_class=debris_class_ids[cls_id],
            ))

    log.info("[DETECTION] debris: %d debris region(s) detected", len(detections))
    return make_model_output(
        "debris", "segmentation", detections, available=True,
        notes="Local YOLOv8-seg model (bounding boxes extracted; segmentation masks available "
              "but not currently surfaced in this schema).",
    )

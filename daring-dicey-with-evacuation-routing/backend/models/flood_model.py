"""
models/flood_model.py

Wraps prithivMLmods/Flood-Image-Detection via transformers image-classification
pipeline. Verified real & working in your floodmodel.ipynb.

HONEST LIMITATION, carried over from your own testing: this is WHOLE-IMAGE
classification only -- 2 labels ("Flooded Scene" / "Non Flooded"), no bbox,
no localization within the image at all. Your own test run showed one real
flood image (flood3.jpg) misclassified as Normal (22.2% flood vs 77.8%
normal) -- documented here as an observed accuracy limitation, not assumed.
"""
import logging
from functools import lru_cache

from transformers import pipeline

from schemas.output_schema import make_detection, make_model_output

log = logging.getLogger("backend.flood_model")

MODEL_ID = "prithivMLmods/Flood-Image-Detection"
FLOOD_LABEL_HUMAN = "Flooding"


@lru_cache(maxsize=1)
def _load_model():
    log.info("[MODEL] Loading flood model...")
    model = pipeline("image-classification", model=MODEL_ID)
    log.info("[MODEL] Flood model loaded")
    return model


def analyze(image_path: str) -> dict:
    try:
        model = _load_model()
    except Exception as e:
        return make_model_output("flood", "classification", [], error=f"model load failed: {e}")

    try:
        results = model(image_path)
    except Exception as e:
        return make_model_output("flood", "classification", [], error=f"inference failed: {e}")

    flood_score = 0.0
    normal_score = 0.0
    for r in results:
        label = r["label"].lower()
        if "non" in label:
            normal_score = r["score"]
        elif "flood" in label:
            flood_score = r["score"]

    detections = []
    if flood_score > normal_score:
        detections.append(
            make_detection(FLOOD_LABEL_HUMAN, flood_score, bbox=None,
                            evidence_type="whole_image", raw_class="Flooded Scene")
        )

    log.info("[DETECTION] flood: flood_score=%.3f normal_score=%.3f", flood_score, normal_score)
    return make_model_output(
        "flood", "classification", detections,
        notes="Whole-image binary classifier -- no bounding box/localization available. "
              "Known false-negative risk observed in source testing.",
    )

"""
inference/model_manager.py

Single point of access to all six model wrappers. Each wrapper already
caches its own loaded model via functools.lru_cache (see models/*.py), so
this module's job is just routing model-name -> analyze() function, keeping
that mapping in one place rather than scattered across the codebase.

GPU/CPU: each individual model wrapper (road/building/fire via ultralytics,
flood via transformers pipeline) auto-detects CUDA through its own library's
default device handling. The earthquake module explicitly detects and logs
CUDA availability itself (see earthquake_detector.py's load_model()).
"""
import logging

from models import road_model, building_model, flood_model, fire_model, earthquake_model, debris_model

log = logging.getLogger("backend.model_manager")

_ANALYZERS = {
    "road": road_model.analyze,
    "building": building_model.analyze,
    "flood": flood_model.analyze,
    "fire": fire_model.analyze,
    "earthquake": earthquake_model.analyze,
    "debris": debris_model.analyze,
}


def run_model(model_name: str, image_path: str) -> dict:
    """
    Runs one model on one image. Never raises -- if the model itself throws
    something its wrapper didn't catch, that's caught here too, so one
    model's failure can never take down the whole pipeline.
    """
    analyzer = _ANALYZERS.get(model_name)
    if analyzer is None:
        return {"model": model_name, "detection_type": None, "detections": [],
                "error": f"unknown model '{model_name}'", "notes": None}
    try:
        return analyzer(image_path)
    except Exception as e:
        log.exception("[MODEL] %s crashed unexpectedly on %s", model_name, image_path)
        return {"model": model_name, "detection_type": None, "detections": [],
                "error": f"unexpected exception: {e}", "notes": None}

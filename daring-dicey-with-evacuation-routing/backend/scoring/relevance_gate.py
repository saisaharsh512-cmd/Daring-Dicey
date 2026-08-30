"""
scoring/relevance_gate.py

THE architectural fix: two CLIP zero-shot gates that must both pass before
any specialized damage model (building/road/fire/debris/earthquake) is
allowed to run on an image. This is what stops a burger photo + "Earthquake"
selected from producing fabricated "Damaged Building" evidence.

Reuses CLIP (openai/clip-vit-base-patch32) -- the same model already used by
the earthquake module -- rather than introducing a new dependency. Loaded as
its own independent instance (not sharing earthquake_detector.py's globals)
so this file can be added without touching that module's preserved
architecture at all. Documented tradeoff: two CLIP instances in memory
instead of one shared instance; both still load once via lru_cache and are
reused across every image/request, so this costs one extra model load, not
repeated downloads or repeated loads per image.

CLIP is NOT a purpose-built disaster classifier. This is a heuristic
zero-shot relevance check, not a certified detector -- exposed honestly via
disaster_probability / non_disaster_probability / confidence / reason, never
presented as more authoritative than it is.

Three-state result: RELEVANT / NOT_RELEVANT / UNCERTAIN. Thresholds are
configurable module constants. Per project requirement, UNCERTAIN must not
silently generate strong damage evidence -- callers (inference_engine.py)
treat UNCERTAIN the same as NOT_RELEVANT for the purpose of gating whether
specialized models run, but the two are reported with different, honest
messages (see make_gate_result's `reason`).
"""
import logging
from functools import lru_cache
from typing import List, Tuple

log = logging.getLogger("backend.relevance_gate")

CLIP_MODEL_ID = "openai/clip-vit-base-patch32"

# Configurable thresholds on disaster_probability (0-1).
GENERAL_RELEVANT_THRESHOLD = 0.60
GENERAL_NOT_RELEVANT_THRESHOLD = 0.35

TYPE_RELEVANT_THRESHOLD = 0.55
TYPE_NOT_RELEVANT_THRESHOLD = 0.30

# --------------------------------------------------------------------------
# Stage 1: general disaster-relatedness prompts
# --------------------------------------------------------------------------
GENERAL_DISASTER_PROMPTS = [
    "a photograph showing earthquake damage or a collapsed building",
    "a photograph showing severe flooding of streets or buildings",
    "a photograph showing a wildfire or large fire with heavy smoke",
    "a photograph showing storm or cyclone damage to structures",
    "a photograph showing a landslide or mudslide covering a road or building",
    "a photograph showing debris and rubble after a disaster",
    "a photograph showing a badly damaged or destroyed road",
    "a photograph of an emergency disaster rescue scene",
]

GENERAL_NORMAL_PROMPTS = [
    "a photograph of food, such as a burger or fries",
    "a photograph of a pet or animal",
    "a photograph of a person in an ordinary everyday setting",
    "a photograph of a car in normal condition on a street",
    "a photograph of a landscape or nature scene with no damage",
    "a photograph of an intact, undamaged building",
    "a screenshot of a computer or phone screen",
    "an ordinary everyday photograph with nothing unusual happening",
]

# --------------------------------------------------------------------------
# Stage 2: disaster-type-specific prompts. "other" has none -- it never gets
# a type gate, per requirement that "Other" must never be silently relabeled.
# --------------------------------------------------------------------------
TYPE_PROMPTS = {
    "earthquake": [
        "a collapsed or heavily cracked building damaged by an earthquake",
        "rubble and debris of a structure destroyed by an earthquake",
    ],
    "flood": [
        "a street or building submerged in flood water",
        "a flooded neighborhood with water covering roads and homes",
    ],
    "fire": [
        "a wildfire burning with visible flames",
        "a building or area filled with smoke from a fire",
    ],
    "wildfire": [
        "a wildfire burning with visible flames",
        "a building or area filled with smoke from a fire",
    ],
    "cyclone": [
        "storm or cyclone damage with debris and downed trees",
        "a building damaged by high winds from a storm",
    ],
    "landslide": [
        "a landslide with mud and rocks covering a road or building",
        "a mudslide burying a structure",
    ],
}


@lru_cache(maxsize=1)
def _load_clip():
    import torch
    from transformers import CLIPModel, CLIPProcessor
    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info("[MODEL] Loading relevance-gate CLIP instance (device=%s)...", device)
    model = CLIPModel.from_pretrained(CLIP_MODEL_ID).to(device).eval()
    processor = CLIPProcessor.from_pretrained(CLIP_MODEL_ID)
    log.info("[MODEL] Relevance-gate CLIP loaded")
    return model, processor, device


def _zero_shot_probs(image_path: str, prompts: List[str]) -> List[float]:
    import torch
    from PIL import Image

    model, processor, device = _load_clip()
    img = Image.open(image_path).convert("RGB")
    inputs = processor(text=prompts, images=img, return_tensors="pt", padding=True).to(device)
    with torch.no_grad():
        outputs = model(**inputs)
        probs = outputs.logits_per_image.softmax(dim=1).cpu().numpy()[0]
    return [float(p) for p in probs]


def _classify(image_path: str, positive_prompts: List[str], negative_prompts: List[str],
              relevant_threshold: float, not_relevant_threshold: float) -> dict:
    all_prompts = positive_prompts + negative_prompts
    probs = _zero_shot_probs(image_path, all_prompts)
    positive_prob = round(sum(probs[: len(positive_prompts)]), 4)
    negative_prob = round(sum(probs[len(positive_prompts):]), 4)

    if positive_prob >= relevant_threshold:
        state = "RELEVANT"
        reason = f"CLIP zero-shot relevance score {positive_prob:.2f} >= threshold {relevant_threshold}"
    elif positive_prob <= not_relevant_threshold:
        state = "NOT_RELEVANT"
        reason = f"CLIP zero-shot relevance score {positive_prob:.2f} <= threshold {not_relevant_threshold}"
    else:
        state = "UNCERTAIN"
        reason = (f"CLIP zero-shot relevance score {positive_prob:.2f} falls between thresholds "
                  f"({not_relevant_threshold}-{relevant_threshold}) -- treated conservatively, "
                  f"specialized models not run")

    return {
        "state": state,
        "positive_probability": positive_prob,
        "negative_probability": negative_prob,
        "confidence": round(max(positive_prob, negative_prob), 4),
        "reason": reason,
    }


def general_disaster_gate(image_path: str) -> dict:
    """Returns {'state', 'positive_probability' (=disaster_probability), 'negative_probability', 'confidence', 'reason'}."""
    try:
        result = _classify(
            image_path, GENERAL_DISASTER_PROMPTS, GENERAL_NORMAL_PROMPTS,
            GENERAL_RELEVANT_THRESHOLD, GENERAL_NOT_RELEVANT_THRESHOLD,
        )
    except Exception as e:
        log.exception("[GATE] general disaster gate failed on %s", image_path)
        # Fail SAFE: a gate that can't run must not let specialized models run either.
        return {"state": "NOT_RELEVANT", "positive_probability": 0.0, "negative_probability": 0.0,
                "confidence": 0.0, "reason": f"gate error (failing safe, treated as not relevant): {e}"}
    log.info("[GATE] general disaster gate: %s (disaster_prob=%.2f)", result["state"], result["positive_probability"])
    return result


def disaster_type_gate(image_path: str, disaster_type: str) -> dict:
    """
    Returns None if disaster_type == 'other' (no type gate applies -- 'other'
    is never checked against a specific category, per requirement).
    Otherwise same shape as general_disaster_gate's result.
    """
    key = (disaster_type or "").strip().lower()
    if key == "other" or key not in TYPE_PROMPTS:
        return None

    positive_prompts = TYPE_PROMPTS[key]
    other_type_prompts = [p for k, prompts in TYPE_PROMPTS.items() if k != key for p in prompts]
    try:
        result = _classify(
            image_path, positive_prompts, other_type_prompts,
            TYPE_RELEVANT_THRESHOLD, TYPE_NOT_RELEVANT_THRESHOLD,
        )
    except Exception as e:
        log.exception("[GATE] type relevance gate failed on %s", image_path)
        return {"state": "NOT_RELEVANT", "positive_probability": 0.0, "negative_probability": 0.0,
                "confidence": 0.0, "reason": f"gate error (failing safe, treated as not relevant): {e}"}
    log.info("[GATE] %s relevance gate: %s (type_prob=%.2f)", key, result["state"], result["positive_probability"])
    return result

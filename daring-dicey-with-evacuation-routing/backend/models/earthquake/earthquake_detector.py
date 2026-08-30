"""
earthquake_detector.py

Image-based earthquake damage TRIAGE tool. NOT a structural safety
certification -- read the disclaimer in analyze_earthquake()'s output
before using this for anything beyond a rough, non-expert visual prototype.

------------------------------------------------------------------------
MODEL CHOICE -- READ THIS BEFORE TRUSTING OUTPUT
------------------------------------------------------------------------
I do not have live web access in the environment that wrote this file,
so I could not browse Hugging Face to verify a purpose-built, ground-level,
single-photo earthquake structural damage classifier exists at a specific
URL. Rather than invent one, here's what's actually used and why:

- xView2/xBD baseline models (real, well-documented, e.g. the
  DIUx-xView/xView2_baseline GitHub repo and published 1st-place
  challenge solutions) were considered and REJECTED for this use case:
  they require PAIRED pre-disaster + post-disaster SATELLITE imagery of
  the same location. Your input is a single ground-level photo -- a
  fundamentally different input format. Using an xBD model here would be
  architecturally wrong, not just suboptimal.

- Instead, this uses CLIP (openai/clip-vit-base-patch32) -- a real,
  verifiable, publicly downloadable pretrained vision-language model via
  the standard `transformers` library -- for ZERO-SHOT classification
  against damage-description text prompts. This is NOT a model trained
  or fine-tuned on labeled earthquake damage data. It is a general
  image-text similarity model repurposed via prompt engineering.

  Practical implication: treat this as a rough triage heuristic, not a
  learned damage detector. It will make mistakes a purpose-trained model
  wouldn't. If you find/verify a real ground-level earthquake damage
  classifier on Hugging Face yourself, swap it in -- the pipeline below
  is structured so the CLIP-specific parts are isolated in
  `_classify_regions()` and `_classify_whole_image()`.

- CLIP does whole-image classification, not object detection. To
  produce bounding-box-style regional output as your spec requires,
  this tiles the image into overlapping grid regions and classifies
  each tile independently. Bounding boxes are therefore GRID CROP
  COORDINATES, not learned object detections. This is a heuristic
  region-estimation strategy, clearly labeled as such in the output
  JSON (`"detection_method": "grid-tile zero-shot classification"`).
------------------------------------------------------------------------
"""

import importlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# STEP 1: Install dependencies
# --------------------------------------------------------------------------
REQUIRED = {
    "torch": "torch",
    "transformers": "transformers",
    "PIL": "pillow",
    "cv2": "opencv-python-headless",
    "numpy": "numpy",
}


def ensure_dependencies():
    for import_name, pip_spec in REQUIRED.items():
        try:
            importlib.import_module(import_name)
            print(f"[ok] {import_name} already available")
        except ImportError:
            print(f"[installing] {pip_spec} ...")
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", pip_spec], check=True)
            print(f"[installed] {pip_spec}")


ensure_dependencies()

import cv2
import numpy as np
import torch
from PIL import Image, UnidentifiedImageError
from transformers import CLIPModel, CLIPProcessor

# --------------------------------------------------------------------------
# Project paths (relative to this file, so it works regardless of cwd)
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
OUTPUTS_DIR = BASE_DIR / "outputs"
TEST_IMAGES_DIR = BASE_DIR / "test_images"

for d in (MODELS_DIR, OUTPUTS_DIR, TEST_IMAGES_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Keep HF's downloaded weights under models/, per the requested project layout.
os.environ.setdefault("HF_HOME", str(MODELS_DIR / "hf_cache"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(MODELS_DIR / "hf_cache"))

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
CLIP_MODEL_ID = "openai/clip-vit-base-patch32"

DISCLAIMER = (
    "This is an automated VISUAL PRELIMINARY ASSESSMENT / TRIAGE tool. "
    "It is NOT a structural safety certification and cannot determine "
    "actual structural integrity. Always obtain a professional structural "
    "engineering inspection before making occupancy or safety decisions."
)

# --------------------------------------------------------------------------
# STEP 2 + 3: Load model, verify it loaded, detect classes/architecture
# --------------------------------------------------------------------------
_model = None
_processor = None
_device = None


def load_model():
    """
    Loads CLIP via the official `transformers` integration (downloads
    weights automatically into models/hf_cache/ on first run). Verifies
    the model actually loaded and reports basic architecture info before
    any inference is attempted.
    """
    global _model, _processor, _device

    _device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"GPU available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU device: {torch.cuda.get_device_name(0)}")
    print(f"Using device: {_device}")

    print(f"\nLoading {CLIP_MODEL_ID} (downloads to {MODELS_DIR / 'hf_cache'} on first run)...")
    try:
        _model = CLIPModel.from_pretrained(CLIP_MODEL_ID).to(_device).eval()
        _processor = CLIPProcessor.from_pretrained(CLIP_MODEL_ID)
    except Exception as e:
        raise RuntimeError(
            f"Failed to load {CLIP_MODEL_ID}. This requires internet access on first "
            f"run to download weights into {MODELS_DIR / 'hf_cache'}. If you're offline, "
            f"download the model on a machine with internet via:\n"
            f"  from transformers import CLIPModel, CLIPProcessor\n"
            f"  CLIPModel.from_pretrained('{CLIP_MODEL_ID}')\n"
            f"  CLIPProcessor.from_pretrained('{CLIP_MODEL_ID}')\n"
            f"then copy the resulting cache folder to {MODELS_DIR / 'hf_cache'}.\n"
            f"Underlying error: {e}"
        )

    cache_path = MODELS_DIR / "hf_cache"
    if not cache_path.exists() or not any(cache_path.iterdir()):
        print("[WARNING] Expected weight cache directory is empty -- model may not have "
              "downloaded correctly, even though loading didn't raise an error.")
    else:
        print(f"[ok] Model weights present under {cache_path}")

    print(f"[ok] Loaded architecture: {_model.config.model_type}, "
          f"vision backbone: {_model.config.vision_config.model_type}, "
          f"projection dim: {_model.config.projection_dim}")
    print("[note] This is a general-purpose zero-shot image-text model, not a model "
          "with fixed earthquake-damage output classes. Classes below are prompt-defined.")

    return _model, _processor, _device


# --------------------------------------------------------------------------
# Damage taxonomy: model's real "classes" are just text prompts (CLIP has
# no fixed label set) -- mapped explicitly to human-readable categories,
# never presented as if they were native model output classes.
# --------------------------------------------------------------------------
SEVERITY_PROMPTS = [
    ("no visible damage, an intact undamaged building wall", "No visible damage", 5),
    ("minor hairline cracks in a building wall", "Minor damage", 20),
    ("major visible wall cracks and structural fractures in a building", "Moderate damage", 45),
    ("partial wall collapse and severe structural deformation of a building", "Severe damage", 70),
    ("complete building collapse with rubble", "Critical / collapse-level damage", 92),
]

DAMAGE_TYPE_PROMPTS = [
    ("hairline cracks in a wall", "Cracks in Walls"),
    ("large major cracks across a wall", "Major Wall Cracks"),
    ("visible structural fracture in a building beam or column", "Structural Fractures"),
    ("partially collapsed wall section", "Partial Wall Collapse"),
    ("damaged or caved-in roof", "Roof Damage"),
    ("fallen debris or structural elements on the ground", "Fallen Structural Elements"),
    ("fully collapsed building", "Building Collapse"),
    ("visibly leaning or deformed building structure", "Severe Deformation"),
]

SEVERITY_LEVEL_THRESHOLDS = [
    (25, "LOW", "Minor visible damage. Continue monitoring and consider inspection."),
    (50, "MODERATE", "Visible damage detected. Professional inspection recommended."),
    (75, "HIGH", "Significant visible structural damage. Restrict access and request professional inspection."),
    (101, "CRITICAL", "Severe/collapse-level visible damage. Evacuate/restrict access and request emergency structural assessment."),
]


def _severity_bucket(score):
    for threshold, level, recommendation in SEVERITY_LEVEL_THRESHOLDS:
        if score < threshold:
            return level, recommendation
    return "CRITICAL", SEVERITY_LEVEL_THRESHOLDS[-1][2]


# --------------------------------------------------------------------------
# STEP 5: Load an input image safely
# --------------------------------------------------------------------------
def validate_and_load_image(image_path):
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type '{path.suffix}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}")
    try:
        img = Image.open(path).convert("RGB")
        img.load()  # forces decode now, so corrupt files fail here, not later mid-pipeline
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError(f"Could not read image at {image_path} -- file may be corrupt: {e}")
    return img


# --------------------------------------------------------------------------
# STEP 6: Run inference (whole-image severity + grid-tile region estimation)
# --------------------------------------------------------------------------
def _clip_similarity(image_crop, text_prompts):
    """
    Runs CLIP zero-shot classification of one image against a list of raw
    text strings. Returns a list of float probabilities, same order as
    text_prompts, summing to 1.0 (softmax over prompts). This function
    knows nothing about label/base_value metadata -- callers attach that
    themselves, so there's no positional tuple-unpacking to get wrong here.
    """
    inputs = _processor(text=text_prompts, images=image_crop, return_tensors="pt", padding=True).to(_device)
    with torch.no_grad():
        outputs = _model(**inputs)
        probs = outputs.logits_per_image.softmax(dim=1).cpu().numpy()[0]
    return [float(p) for p in probs]


def _rank_severity(image_crop):
    """
    Ranks image_crop against SEVERITY_PROMPTS. Returns a list of dicts,
    each with EXPLICITLY TYPED fields, sorted by confidence descending:
      {"label": str, "base_value": float, "confidence": float}
    SEVERITY_PROMPTS rows are (prompt_text, label, base_value) -- unpacked
    here by name, once, in the one place that knows this schema.
    """
    probs = _clip_similarity(image_crop, [row[0] for row in SEVERITY_PROMPTS])
    ranked = sorted(
        (
            {"label": str(label), "base_value": float(base_value), "confidence": float(prob)}
            for (_, label, base_value), prob in zip(SEVERITY_PROMPTS, probs)
        ),
        key=lambda r: -r["confidence"],
    )
    return ranked


def _rank_damage_types(image_crop):
    """
    Ranks image_crop against DAMAGE_TYPE_PROMPTS. Returns a list of dicts:
      {"label": str, "confidence": float}
    DAMAGE_TYPE_PROMPTS rows are (prompt_text, label) -- unpacked by name,
    once, in the one place that knows this schema.
    """
    probs = _clip_similarity(image_crop, [row[0] for row in DAMAGE_TYPE_PROMPTS])
    ranked = sorted(
        (
            {"label": str(label), "confidence": float(prob)}
            for (_, label), prob in zip(DAMAGE_TYPE_PROMPTS, probs)
        ),
        key=lambda r: -r["confidence"],
    )
    return ranked


def _classify_whole_image(pil_img):
    """Returns (label: str, base_value: float, confidence: float) -- always these types, always this order."""
    top = _rank_severity(pil_img)[0]
    label = top["label"]
    base_value = top["base_value"]
    confidence = round(top["confidence"], 4)
    assert isinstance(label, str) and isinstance(base_value, float) and isinstance(confidence, float), (
        f"_classify_whole_image produced unexpected types: "
        f"label={type(label)}, base_value={type(base_value)}, confidence={type(confidence)}"
    )
    return label, base_value, confidence


def _grid_tiles(pil_img, grid=3, overlap=0.25):
    """Yields (x1, y1, x2, y2) bboxes for overlapping tiles across the image."""
    w, h = pil_img.size
    tile_w, tile_h = w / grid, h / grid
    step_w, step_h = tile_w * (1 - overlap), tile_h * (1 - overlap)

    tiles = []
    y = 0.0
    while y < h:
        x = 0.0
        x2 = y2 = 0.0
        while x < w:
            x2, y2 = min(x + tile_w, w), min(y + tile_h, h)
            if x2 - x > 20 and y2 - y > 20:  # skip slivers at edges
                tiles.append((x, y, x2, y2))
            x += step_w
            if x2 >= w:
                break
        y += step_h
        if y2 >= h:
            break
    return tiles


def _classify_regions(pil_img, damage_prob_floor=0.30):
    """
    Grid-tile zero-shot damage-type classification. NOT object detection --
    see module docstring. Flags a tile as a "detection" only if its top
    damage-type match beats damage_prob_floor AND the whole-tile severity
    prompt set doesn't call it confidently undamaged.
    """
    detections = []
    img_w, img_h = pil_img.size
    img_area = img_w * img_h

    for (x1, y1, x2, y2) in _grid_tiles(pil_img):
        crop = pil_img.crop((x1, y1, x2, y2))

        top_severity = _rank_severity(crop)[0]
        top_severity_label = top_severity["label"]        # str
        top_severity_conf = top_severity["confidence"]      # float

        if top_severity_label == "No visible damage" and top_severity_conf > 0.5:
            continue  # skip tiles CLIP is fairly confident are undamaged

        top_damage = _rank_damage_types(crop)[0]
        damage_label = top_damage["label"]        # str
        damage_conf = top_damage["confidence"]     # float

        if damage_conf < damage_prob_floor:
            continue

        box_w, box_h = x2 - x1, y2 - y1
        area_pct = round((box_w * box_h / img_area) * 100, 2) if img_area > 0 else 0.0

        detections.append({
            "damage_type": damage_label,
            "severity": top_severity_label,
            "confidence": round(damage_conf, 4),
            "bbox": {"x1": round(x1, 1), "y1": round(y1, 1), "x2": round(x2, 1), "y2": round(y2, 1)},
            "bbox_width": round(box_w, 1),
            "bbox_height": round(box_h, 1),
            "area_percent_of_image": area_pct,
        })

    return detections


# --------------------------------------------------------------------------
# STEP 7 + 8: Affected area + prototype severity score (0-100)
#
# Confidence is NOT severity. Severity blends:
#   - overall severity category (from whole-image classification)
#   - number of damaged regions found
#   - total affected area across regions
#   - presence of collapse / major-structural damage types specifically
# Confidence only softens each region's contribution -- it never drives
# the score alone.
# --------------------------------------------------------------------------
COLLAPSE_TYPES = {"Building Collapse", "Partial Wall Collapse", "Fallen Structural Elements"}
MAJOR_STRUCTURAL_TYPES = {"Structural Fractures", "Major Wall Cracks", "Severe Deformation"}


def calculate_severity(whole_image_label, whole_image_base, whole_image_conf, detections):
    """
    Calculate a conservative 0-100 TRIAGE score.

    Important:
    CLIP is a whole-image zero-shot classifier, not an object detector.
    Grid tiles are therefore treated only as REGIONAL EVIDENCE. We do not
    sum their overlapping areas and we do not treat each tile as a separate
    physical damaged object.
    """
    if not isinstance(whole_image_label, str):
        raise TypeError(
            f"whole_image_label must be str, got {type(whole_image_label)}: "
            f"{whole_image_label!r}"
        )
    if not isinstance(whole_image_base, (int, float)):
        raise TypeError(
            f"whole_image_base must be numeric, got {type(whole_image_base)}: "
            f"{whole_image_base!r}"
        )
    if not isinstance(whole_image_conf, (int, float)):
        raise TypeError(
            f"whole_image_conf must be numeric, got {type(whole_image_conf)}: "
            f"{whole_image_conf!r}"
        )

    # Whole-image classification is the primary signal.
    score = float(whole_image_base) * (0.65 + 0.35 * float(whole_image_conf))

    # Regional evidence is a small supporting signal only.
    if detections:
        # Number of unique grid regions is evidence, not object count.
        region_evidence = min(len(detections), 9) / 9.0
        score += 8.0 * region_evidence

        collapse_count = sum(
            1 for d in detections if d.get("damage_type") in COLLAPSE_TYPES
        )
        major_count = sum(
            1 for d in detections if d.get("damage_type") in MAJOR_STRUCTURAL_TYPES
        )

        # Strong structural evidence gets a modest bonus.
        if collapse_count:
            score += 7.0
        elif major_count:
            score += 4.0

    # Keep score in the declared 0-100 range.
    score = round(min(max(score, 0.0), 100.0), 1)
    level, recommendation = _severity_bucket(score)

    # Do NOT claim an exact affected area from overlapping CLIP tiles.
    # The model does not produce true damage segmentation.
    return score, level, recommendation, None


# --------------------------------------------------------------------------
# STEP 9: Annotated image
# --------------------------------------------------------------------------
def draw_annotations(pil_img, detections, save_path):
    img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    for d in detections:
        x1, y1 = int(d["bbox"]["x1"]), int(d["bbox"]["y1"])
        x2, y2 = int(d["bbox"]["x2"]), int(d["bbox"]["y2"])
        color = (0, 0, 255) if d["damage_type"] in COLLAPSE_TYPES else (0, 140, 255)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = f"Regional evidence: {d['damage_type']} ({d['confidence']:.2f})"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(img, (x1, max(0, y1 - th - 6)), (x1 + tw + 4, y1), color, -1)
        cv2.putText(img, label, (x1 + 2, y1 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(save_path), img)
    return save_path


# --------------------------------------------------------------------------
# STEP 10 + 11: JSON report + single entry-point function
# --------------------------------------------------------------------------
def analyze_earthquake(image_path, save_outputs=True):
    """
    Full earthquake damage TRIAGE pipeline. See module docstring for the
    model-choice explanation and its limitations before trusting output.

    Returns a classification-first earthquake triage report, plus:
      - "disclaimer": explicit non-certification notice (always present)
      - "regional_evidence": supporting CLIP grid regions, not physical detections
      - "annotated_image_array": BGR numpy array (cv2 format), for
        in-memory use without touching disk
    """
    global _model
    if _model is None:
        load_model()

    pil_img = validate_and_load_image(image_path)
    img_w, img_h = pil_img.size

    whole_label, whole_base, whole_conf = _classify_whole_image(pil_img)

    # Regional CLIP tiles are retained as supporting evidence only.
    detections = _classify_regions(pil_img)

    score, level, recommendation, total_area_pct = calculate_severity(
        whole_label, whole_base, whole_conf, detections
    )

    annotated_path = OUTPUTS_DIR / "earthquake_annotated.jpg"
    if save_outputs:
        draw_annotations(pil_img, detections, annotated_path)

    result = {
        "hazard": "earthquake",
        "damage_detected": len(detections) > 0 or whole_label != "No visible damage",
        "overall_severity": level,
        "severity_score": score,
        "whole_image_classification": {
            "label": whole_label,
            "confidence": whole_conf,
        },
        "total_affected_area_percent": None,
        "affected_area_note": (
            "Not estimated as a percentage because CLIP grid tiles overlap and "
            "are regional evidence rather than true damage segmentation."
        ),
        "regional_evidence": [
            {
                "region_type": "supporting_evidence",
                "damage_type": d["damage_type"],
                "severity": d["severity"],
                "confidence": d["confidence"],
                "grid_bbox": [
                    d["bbox"]["x1"],
                    d["bbox"]["y1"],
                    d["bbox"]["x2"],
                    d["bbox"]["y2"],
                ],
            }
            for d in detections
        ],
        "regional_evidence_count": len(detections),
        "detection_method": (
            "CLIP whole-image zero-shot classification with overlapping grid "
            "regional evidence; NOT a trained object detector or damage segmentation model"
        ),
        "recommendation": recommendation,
        "disclaimer": DISCLAIMER,
        "image_width": img_w,
        "image_height": img_h,
        "analyzed_at_utc": datetime.now(timezone.utc).isoformat(),
        "annotated_image_path": str(annotated_path) if save_outputs else None,
    }

    if save_outputs:
        report_path = OUTPUTS_DIR / f"report_{Path(image_path).stem}.json"
        with open(report_path, "w") as f:
            json.dump(result, f, indent=2)
        result["report_path"] = str(report_path)
        print(f"\nReport saved to: {report_path}")
        print(f"Annotated image saved to: {annotated_path}")

    result["annotated_image_array"] = cv2.imread(str(annotated_path)) if save_outputs and annotated_path.exists() else None

    return result


if __name__ == "__main__":
    load_model()
    print(f"\nPlace a test image in {TEST_IMAGES_DIR} and run:")
    print("  from earthquake_detector import analyze_earthquake")
    print("  result = analyze_earthquake('test_images/your_image.jpg')")

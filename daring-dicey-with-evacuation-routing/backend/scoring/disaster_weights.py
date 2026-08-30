"""
scoring/disaster_weights.py

The two explainable tables that drive severity scoring. No neural network,
no opaque logic -- every number here is a documented judgment call you can
defend to a judge by reading this file top to bottom.

TABLE 1: BASE_SEVERITY -- "how bad is this type of damage, inherently,
regardless of which model saw it or how confident it was?" Derived from each
model's own actual class semantics (see backend audit / README), not
invented. 0-100 scale.

TABLE 2: DISASTER_MODEL_WEIGHTS -- "how relevant is each model's evidence to
THIS disaster type?" A pothole matters less during an earthquake response
than a collapsed building does; flooding matters enormously during a flood
and barely at all during a wildfire. These are relative multipliers, not
probabilities -- they don't need to sum to 1.
"""

# --------------------------------------------------------------------------
# TABLE 1: per-damage-type base severity (0-100), grounded in real classes
# --------------------------------------------------------------------------

ROAD_BASE_SEVERITY = {
    "Pothole": 90,
    "Alligator Crack": 75,
    "Block Crack": 45,
    "Unspecified Crack": 45,
    "Edge Crack": 40,
    "Longitudinal Crack": 35,
    "Transverse Crack": 35,
}

BUILDING_BASE_SEVERITY = {
    # Binary detector -- one damage class, flat base. Refined by confidence
    # and corroborating detection count at the location-aggregation stage,
    # not here (there is no class-level gradation to draw on).
    "Damaged Building": 75,
}

FLOOD_BASE_SEVERITY = {
    # Whole-image binary classifier -- confidence itself carries most of the
    # signal here since there's no localization or gradation to lean on.
    "Flooding": 65,
}

FIRE_BASE_SEVERITY = {
    "Fire": 90,       # active fire -- immediate, severe
    "Smoke": 55,       # precursor/consequence signal, less severe than active fire
}

EARTHQUAKE_BASE_SEVERITY = {
    # Mirrors earthquake_detector.py's own internal severity vocabulary so
    # the unified engine doesn't contradict the module's own judgments.
    "No visible damage": 5,
    "Minor damage": 20,
    "Moderate damage": 45,
    "Severe damage": 70,
    "Critical / collapse-level damage": 92,
    "Building Collapse": 100,
    "Partial Wall Collapse": 90,
    "Fallen Structural Elements": 80,
    "Structural Fractures": 75,
    "Major Wall Cracks": 70,
    "Severe Deformation": 70,
    "Roof Damage": 55,
    "Cracks in Walls": 30,
}

DEBRIS_BASE_SEVERITY = {
    # New local model (RescueNet YOLOv8-seg) reports a single "Debris" class.
    "Debris": 55,
}
DEBRIS_DEFAULT_SEVERITY = 50

BASE_SEVERITY_TABLES = {
    "road": ROAD_BASE_SEVERITY,
    "building": BUILDING_BASE_SEVERITY,
    "flood": FLOOD_BASE_SEVERITY,
    "fire": FIRE_BASE_SEVERITY,
    "earthquake": EARTHQUAKE_BASE_SEVERITY,
    "debris": DEBRIS_BASE_SEVERITY,
}

DEFAULT_BASE_SEVERITY = 50  # fallback for any damage_type not in a model's table


def get_base_severity(model: str, damage_type: str) -> float:
    table = BASE_SEVERITY_TABLES.get(model, {})
    if model == "debris":
        return table.get(damage_type, DEBRIS_DEFAULT_SEVERITY)
    return table.get(damage_type, DEFAULT_BASE_SEVERITY)


# --------------------------------------------------------------------------
# TABLE 2: disaster-aware model relevance weights (0.0-1.0 multipliers)
# --------------------------------------------------------------------------
# Reasoning documented per disaster type. A model can still run and be
# reported even at low weight (e.g. fire during a flood) -- weight controls
# how much that evidence counts toward the location severity score, not
# whether it's shown at all.

DISASTER_MODEL_WEIGHTS = {
    "earthquake": {
        "earthquake": 1.0,   # primary signal for this disaster type
        "building": 1.0,     # structural collapse is the core earthquake risk
        "debris": 0.8,       # fallen material strongly correlates with structural failure
        "road": 0.7,         # blocked roads matter a lot for rescue access
        "fire": 0.3,         # secondary -- gas-line/electrical fires do follow earthquakes
        "flood": 0.1,        # rare secondary effect (burst water mains) -- low but nonzero
    },
    "flood": {
        "flood": 1.0,        # primary signal
        "road": 0.8,         # flooded/impassable roads critical for evacuation routing
        "building": 0.6,     # water damage matters but building model can't see water itself
        "debris": 0.5,       # floating/deposited debris after flooding
        "earthquake": 0.2,   # rarely co-occurs, kept low not zero
        "fire": 0.1,         # rare (electrical faults) -- low but nonzero
    },
    "wildfire": {
        "fire": 1.0,         # primary signal
        "building": 0.6,     # structures in fire path
        "road": 0.5,         # smoke/fire road blockages
        "debris": 0.4,       # burned structural debris
        "flood": 0.1,        # essentially irrelevant, kept low not zero
        "earthquake": 0.1,   # essentially irrelevant, kept low not zero
    },
    "cyclone": {
        "building": 0.9,     # wind/structural damage is the primary visible signal
        "road": 0.7,         # downed trees/debris blocking roads
        "debris": 0.7,       # storm debris strongly correlates with cyclone damage
        "flood": 0.5,        # storm surge/rain flooding often co-occurs
        "fire": 0.1,
        "earthquake": 0.1,
    },
    "landslide": {
        "debris": 1.0,       # primary visible signal -- mud/rock/debris covering the scene
        "road": 0.8,         # landslides very commonly bury/block roads
        "building": 0.6,     # structures can be damaged/buried
        "flood": 0.1,
        "fire": 0.1,
        "earthquake": 0.1,
    },
    "other": {
        # Deliberately flat and moderate -- "other" makes no claim about
        # which evidence type matters most, since the specific disaster
        # category is unknown/unclassified by design.
        "building": 0.6, "road": 0.6, "fire": 0.6, "debris": 0.6, "flood": 0.4, "earthquake": 0.3,
    },
}
DISASTER_MODEL_WEIGHTS["fire"] = DISASTER_MODEL_WEIGHTS["wildfire"]  # alias

DEFAULT_MODEL_WEIGHTS = {  # unrecognized disaster_type: run everything, weight equally
    "road": 0.6, "building": 0.6, "flood": 0.6, "fire": 0.6, "earthquake": 0.6, "debris": 0.6,
}

# --------------------------------------------------------------------------
# Disaster-aware model ROUTING: which models actually RUN per disaster type.
# Distinct from weighting above -- this controls execution, not scoring.
# A model is only skipped when it is genuinely disaster-irrelevant; models
# that "may also produce" relevant signals (per project instructions) stay
# in the run list even at low weight.
# --------------------------------------------------------------------------

DISASTER_MODEL_ROUTES = {
    "earthquake": {"run": ["earthquake", "building", "debris", "road", "fire"], "skip": ["flood"]},
    "flood": {"run": ["flood", "road", "building", "debris"], "skip": ["fire", "earthquake"]},
    "wildfire": {"run": ["fire", "building", "road", "debris"], "skip": ["flood", "earthquake"]},
    # No dedicated cyclone/landslide/other detector exists -- these route to
    # the existing models that plausibly produce relevant supporting evidence,
    # never to a model claiming a category it wasn't trained for.
    "cyclone": {"run": ["building", "road", "debris", "flood"], "skip": ["fire", "earthquake"]},
    "landslide": {"run": ["debris", "road", "building"], "skip": ["fire", "flood", "earthquake"]},
    "other": {"run": ["building", "road", "fire", "debris"], "skip": ["flood", "earthquake"]},
}
DISASTER_MODEL_ROUTES["fire"] = DISASTER_MODEL_ROUTES["wildfire"]  # alias

ALL_MODELS = ["road", "building", "flood", "fire", "earthquake", "debris"]


def get_route(disaster_type: str) -> dict:
    """Returns {'run': [...], 'skip': [...]}. Unknown disaster_type runs everything."""
    key = (disaster_type or "").strip().lower()
    if key in DISASTER_MODEL_ROUTES:
        return DISASTER_MODEL_ROUTES[key]
    return {"run": list(ALL_MODELS), "skip": []}


def get_weights(disaster_type: str) -> dict:
    key = (disaster_type or "").strip().lower()
    return DISASTER_MODEL_WEIGHTS.get(key, DEFAULT_MODEL_WEIGHTS)

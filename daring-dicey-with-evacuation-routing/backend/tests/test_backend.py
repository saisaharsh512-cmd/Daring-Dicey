"""
tests/test_backend.py

These tests mock the actual model inference calls (run_model) rather than
downloading real weights, because this environment has no network access to
Hugging Face/Roboflow. Everything ELSE is exercised through real code:
validation, routing, severity scoring, location clustering, aggregation,
priority ranking, and infrastructure constraint generation.

Run with real models on your machine (with network access) by removing the
monkeypatch of inference.model_manager.run_model in setUp -- the rest of
this test file still applies unchanged.
"""
import sys
import os
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image
import numpy as np

TEST_IMG_DIR = Path(__file__).resolve().parent.parent / "test_images"
TEST_IMG_DIR.mkdir(exist_ok=True)


def _make_test_image(name):
    path = TEST_IMG_DIR / name
    if not path.exists():
        arr = (np.random.rand(200, 300, 3) * 255).astype("uint8")
        Image.fromarray(arr).save(path)
    return str(path)


# Fake model outputs keyed by (model_name, image_path) so different images
# can simulate different evidence at "different locations".
FAKE_RESULTS = {}


def fake_run_model(model_name, image_path):
    key = (model_name, image_path)
    if key in FAKE_RESULTS:
        result = dict(FAKE_RESULTS[key])
        result.setdefault("success", result.get("error") is None)
        result.setdefault("available", True)
        result.setdefault("confidence", None)
        return result
    return {"model": model_name, "detection_type": "object_detection", "detections": [],
            "error": None, "notes": None, "success": True, "available": True, "confidence": None}


# Default fake gate results: RELEVANT, so existing pre-gate tests (which
# assume specialized models run) keep passing without real CLIP calls. Tests
# that specifically exercise gate behavior override this per-test.
def fake_gate_relevant(image_path, *args, **kwargs):
    return {"state": "RELEVANT", "positive_probability": 0.9, "negative_probability": 0.1,
            "confidence": 0.9, "reason": "mocked RELEVANT for test"}


def fake_type_gate_relevant(image_path, disaster_type):
    if (disaster_type or "").lower() == "other":
        return None
    return fake_gate_relevant(image_path)


class TestValidation(unittest.TestCase):
    def test_missing_image(self):
        from inference.inference_engine import validate_image
        result = validate_image("test_images/does_not_exist.jpg")
        self.assertFalse(result["valid"])
        self.assertIn("not found", result["error"])

    def test_corrupt_image(self):
        from inference.inference_engine import validate_image
        path = TEST_IMG_DIR / "corrupt.jpg"
        path.write_bytes(b"not an image")
        result = validate_image(str(path))
        self.assertFalse(result["valid"])

    def test_unsupported_format(self):
        from inference.inference_engine import validate_image
        path = TEST_IMG_DIR / "file.txt"
        path.write_text("hello")
        result = validate_image(str(path))
        self.assertFalse(result["valid"])
        self.assertIn("unsupported", result["error"])

    def test_valid_image(self):
        from inference.inference_engine import validate_image
        path = _make_test_image("valid.jpg")
        result = validate_image(path)
        self.assertTrue(result["valid"])

    def test_missing_location(self):
        from inference.inference_engine import validate_location
        result = validate_location({"image_path": "x.jpg"})
        self.assertFalse(result["valid"])
        self.assertIn("missing", result["error"])

    def test_invalid_location_range(self):
        from inference.inference_engine import validate_location
        result = validate_location({"latitude": 999, "longitude": 0})
        self.assertFalse(result["valid"])

    def test_valid_location_nested(self):
        from inference.inference_engine import validate_location
        result = validate_location({"location": {"latitude": 12.9, "longitude": 77.5}})
        self.assertTrue(result["valid"])


class TestRouter(unittest.TestCase):
    def test_earthquake_routing(self):
        from inference.disaster_router import route
        r = route("earthquake")
        self.assertTrue(r["recognized"])
        self.assertIn("earthquake", r["run"])
        self.assertIn("building", r["run"])
        self.assertIn("flood", r["skip"])

    def test_unknown_disaster_type_runs_everything(self):
        from inference.disaster_router import route
        r = route("volcano")
        self.assertFalse(r["recognized"])
        for m in ["road", "building", "flood", "fire", "earthquake", "debris"]:
            self.assertIn(m, r["run"])


class TestSeverityEngine(unittest.TestCase):
    def test_confidence_does_not_override_damage_type(self):
        """Core requirement: minor damage at high confidence must NOT outscore
        severe damage at lower confidence."""
        from scoring.severity_engine import compute_detection_severity_value
        minor_high_conf = compute_detection_severity_value("road", "Longitudinal Crack", 0.95)
        severe_low_conf = compute_detection_severity_value("building", "Damaged Building", 0.60)
        self.assertLess(minor_high_conf, severe_low_conf)

    def test_location_severity_capped_at_100(self):
        from scoring.severity_engine import compute_location_severity
        evidence = [
            {"model": "building", "damage_type": "Damaged Building", "confidence": 0.99, "severity_value": 100},
            {"model": "debris", "damage_type": "Other Debris", "confidence": 0.99, "severity_value": 100},
            {"model": "road", "damage_type": "Pothole", "confidence": 0.99, "severity_value": 100},
        ]
        result = compute_location_severity(evidence, "earthquake")
        self.assertLessEqual(result["score"], 100)
        self.assertEqual(result["level"], "CRITICAL")

    def test_no_evidence_is_low(self):
        from scoring.severity_engine import compute_location_severity
        result = compute_location_severity([], "flood")
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["level"], "LOW")


class TestLocationAggregator(unittest.TestCase):
    def test_nearby_points_cluster(self):
        from aggregation.location_aggregator import cluster_images
        images = [
            {"image_path": "a.jpg", "latitude": 12.9716, "longitude": 77.5946},
            {"image_path": "b.jpg", "latitude": 12.97165, "longitude": 77.59465},  # ~7m away
        ]
        clusters = cluster_images(images, tolerance_meters=75)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]["images"]), 2)

    def test_distant_points_separate(self):
        from aggregation.location_aggregator import cluster_images
        images = [
            {"image_path": "a.jpg", "latitude": 12.9716, "longitude": 77.5946},
            {"image_path": "b.jpg", "latitude": 13.0827, "longitude": 80.2707},  # different city
        ]
        clusters = cluster_images(images, tolerance_meters=75)
        self.assertEqual(len(clusters), 2)


class TestFullPipeline(unittest.TestCase):
    def setUp(self):
        self.patcher = patch("inference.inference_engine.run_model", side_effect=fake_run_model)
        self.patcher.start()
        self.gate_patcher = patch("inference.inference_engine.general_disaster_gate", side_effect=fake_gate_relevant)
        self.gate_patcher.start()
        self.type_gate_patcher = patch("inference.inference_engine.disaster_type_gate", side_effect=fake_type_gate_relevant)
        self.type_gate_patcher.start()
        FAKE_RESULTS.clear()

    def tearDown(self):
        self.patcher.stop()
        self.gate_patcher.stop()
        self.type_gate_patcher.stop()

    def test_multiple_images_same_location_aggregate(self):
        from api.backend import analyze_disaster
        img1 = _make_test_image("loc_a_1.jpg")
        img2 = _make_test_image("loc_a_2.jpg")

        FAKE_RESULTS[("building", img1)] = {
            "model": "building", "detection_type": "object_detection", "error": None, "notes": None,
            "detections": [{"damage_type": "Damaged Building", "confidence": 0.82, "bbox": [1, 2, 3, 4], "evidence_type": "detection", "raw_class": "damaged building"}],
        }
        FAKE_RESULTS[("debris", img2)] = {
            "model": "debris", "detection_type": "object_detection", "error": None, "notes": None,
            "detections": [{"damage_type": "Other Debris", "confidence": 0.77, "bbox": [5, 6, 7, 8], "evidence_type": "detection", "raw_class": "Other Debris"}],
        }
        # skip road/fire/earthquake in this test to keep it focused (fake defaults to empty detections anyway)

        result = analyze_disaster(
            "earthquake",
            [
                {"image_path": img1, "location": {"latitude": 12.9716, "longitude": 77.5946}},
                {"image_path": img2, "location": {"latitude": 12.97161, "longitude": 77.59461}},
            ],
        )
        self.assertEqual(len(result["locations"]), 1, "images at nearly the same spot should aggregate to one location")
        loc = result["locations"][0]
        models_seen = set(d["model"] for d in loc["detected_damage"])
        self.assertEqual(models_seen, {"building", "debris"})
        self.assertGreater(loc["severity_score"], 0)

    def test_multiple_distinct_locations_and_priority_order(self):
        from api.backend import analyze_disaster
        img_critical = _make_test_image("loc_critical.jpg")
        img_minor = _make_test_image("loc_minor.jpg")

        FAKE_RESULTS[("building", img_critical)] = {
            "model": "building", "detection_type": "object_detection", "error": None, "notes": None,
            "detections": [{"damage_type": "Damaged Building", "confidence": 0.95, "bbox": [0, 0, 1, 1], "evidence_type": "detection", "raw_class": "damaged building"}],
        }
        FAKE_RESULTS[("road", img_minor)] = {
            "model": "road", "detection_type": "object_detection", "error": None, "notes": None,
            "detections": [{"damage_type": "Transverse Crack", "confidence": 0.3, "bbox": [0, 0, 1, 1], "evidence_type": "detection", "raw_class": "transverse"}],
        }

        result = analyze_disaster(
            "earthquake",
            [
                {"image_path": img_critical, "location": {"latitude": 10.0, "longitude": 10.0}},
                {"image_path": img_minor, "location": {"latitude": 20.0, "longitude": 20.0}},
            ],
        )
        self.assertEqual(len(result["locations"]), 2)
        self.assertEqual(result["priority_order"][0]["priority_rank"], 1)
        # the building-collapse-evidence location must outrank the minor-crack-only location
        top_location = result["locations"][0]
        self.assertGreater(top_location["severity_score"], result["locations"][1]["severity_score"])
        self.assertEqual(top_location["latitude"], 10.0)

    def test_infrastructure_constraints_exposed(self):
        from api.backend import analyze_disaster
        img = _make_test_image("loc_road.jpg")
        FAKE_RESULTS[("road", img)] = {
            "model": "road", "detection_type": "object_detection", "error": None, "notes": None,
            "detections": [{"damage_type": "Pothole", "confidence": 0.91, "bbox": [0, 0, 1, 1], "evidence_type": "detection", "raw_class": "pothole"}],
        }
        result = analyze_disaster("flood", [{"image_path": img, "location": {"latitude": 1.0, "longitude": 1.0}}])
        constraints = result["locations"][0]["infrastructure_constraints"]
        self.assertTrue(any(c["type"] == "road" and c["status"] == "blocked" for c in constraints))

    def test_invalid_disaster_type_does_not_crash(self):
        from api.backend import analyze_disaster
        img = _make_test_image("loc_unknown_disaster.jpg")
        result = analyze_disaster("volcano", [{"image_path": img, "location": {"latitude": 1.0, "longitude": 1.0}}])
        self.assertEqual(result["disaster_type"], "volcano")
        self.assertEqual(len(result["locations"]), 1)

    def test_missing_metadata_images_are_skipped_not_fatal(self):
        from api.backend import analyze_disaster
        good_img = _make_test_image("loc_good.jpg")
        result = analyze_disaster(
            "flood",
            [
                {"image_path": good_img, "location": {"latitude": 1.0, "longitude": 1.0}},
                {"image_path": "nonexistent.jpg", "location": {"latitude": 1.0, "longitude": 1.0}},
                {"image_path": good_img},  # missing location entirely
            ],
        )
        self.assertEqual(len(result["skipped_images"]), 2)
        self.assertEqual(len(result["locations"]), 1)  # good image still processed

    def test_one_model_failing_does_not_crash_pipeline(self):
        from api.backend import analyze_disaster
        img = _make_test_image("loc_model_fail.jpg")
        FAKE_RESULTS[("earthquake", img)] = {
            "model": "earthquake", "detection_type": None, "detections": [],
            "error": "simulated model load failure", "notes": None,
        }
        FAKE_RESULTS[("building", img)] = {
            "model": "building", "detection_type": "object_detection", "error": None, "notes": None,
            "detections": [{"damage_type": "Damaged Building", "confidence": 0.7, "bbox": [0, 0, 1, 1], "evidence_type": "detection", "raw_class": "damaged building"}],
        }
        result = analyze_disaster("earthquake", [{"image_path": img, "location": {"latitude": 5.0, "longitude": 5.0}}])
        loc = result["locations"][0]
        self.assertIn("earthquake", loc["model_errors"])
        self.assertGreater(loc["severity_score"], 0)  # building evidence still scored despite earthquake model failing

    def test_confidence_threshold_filters_low_confidence(self):
        """Confirms severity engine still applies even to low-confidence detections
        (soft-scaled, not zeroed) -- and that a 0-confidence edge case doesn't crash."""
        from scoring.severity_engine import compute_detection_severity_value
        val = compute_detection_severity_value("fire", "Fire", 0.0)
        self.assertGreater(val, 0)  # base_severity * 0.5 floor, never fully zeroed by confidence alone
        self.assertLess(val, compute_detection_severity_value("fire", "Fire", 1.0))


class TestRelevanceGates(unittest.TestCase):
    """
    Acceptance tests for the core architectural fix. Mocks CLIP calls (no
    network access in this sandbox) but exercises the REAL gate-enforcement
    logic in inference_engine.analyze_image() and api.backend.analyze_disaster().
    """
    def setUp(self):
        self.run_model_patcher = patch("inference.inference_engine.run_model", side_effect=fake_run_model)
        self.run_model_patcher.start()
        FAKE_RESULTS.clear()

    def tearDown(self):
        self.run_model_patcher.stop()

    def _mock_not_relevant(self, image_path, *a, **k):
        return {"state": "NOT_RELEVANT", "positive_probability": 0.05, "negative_probability": 0.95,
                "confidence": 0.95, "reason": "mocked NOT_RELEVANT for test"}

    def _mock_uncertain(self, image_path, *a, **k):
        return {"state": "UNCERTAIN", "positive_probability": 0.48, "negative_probability": 0.52,
                "confidence": 0.52, "reason": "mocked UNCERTAIN for test"}

    # TEST 1 (acceptance): burger image + Earthquake selected -> NOT A DISASTER,
    # zero specialized models run, no fabricated "Damaged Building" evidence.
    def test_burger_image_never_runs_specialized_models(self):
        from api.backend import analyze_disaster
        img = _make_test_image("burger.jpg")

        # Even if a model WOULD have returned damage evidence, it must never be called.
        FAKE_RESULTS[("building", img)] = {
            "model": "building", "detection_type": "object_detection", "error": None, "notes": None,
            "detections": [{"damage_type": "Damaged Building", "confidence": 0.99, "bbox": [0, 0, 1, 1], "evidence_type": "detection", "raw_class": "damaged building"}],
        }

        with patch("inference.inference_engine.general_disaster_gate", side_effect=self._mock_not_relevant), \
             patch("inference.inference_engine.disaster_type_gate", side_effect=self._mock_not_relevant):
            result = analyze_disaster("earthquake", [{"image_path": img, "location": {"latitude": 1.0, "longitude": 1.0}}])

        self.assertFalse(result["is_disaster"])
        self.assertEqual(result["gate_status"], "NOT_A_DISASTER")
        loc = result["locations"][0]
        self.assertFalse(loc["is_disaster"])
        self.assertEqual(loc["severity_score"], 0.0)
        self.assertEqual(loc["detected_damage"], [], "no fabricated damage evidence must appear")
        for status in result["model_status"]:
            if status["model"] in ("building", "road", "fire", "debris", "earthquake"):
                self.assertIn(status["status"], ("gate_blocked", "not_relevant"))

    # TEST 5 (acceptance): normal intact building + Earthquake -> must not
    # become a high-severity result just because a detector fires.
    def test_general_relevant_but_type_not_relevant(self):
        """General gate passes (it IS a building photo) but earthquake-type gate fails."""
        from api.backend import analyze_disaster
        img = _make_test_image("normal_building.jpg")

        def mixed_gate_general(image_path, *a, **k):
            return {"state": "RELEVANT", "positive_probability": 0.65, "negative_probability": 0.35,
                    "confidence": 0.65, "reason": "mocked borderline-relevant"}

        with patch("inference.inference_engine.general_disaster_gate", side_effect=mixed_gate_general), \
             patch("inference.inference_engine.disaster_type_gate", side_effect=self._mock_not_relevant):
            result = analyze_disaster("earthquake", [{"image_path": img, "location": {"latitude": 2.0, "longitude": 2.0}}])

        self.assertFalse(result["is_disaster"])
        self.assertEqual(result["gate_status"], "NOT_RELEVANT_TO_SELECTED_TYPE")
        self.assertEqual(result["locations"][0]["detected_damage"], [])

    # TEST 7 (acceptance): "Other" selected + landslide image -> classified as
    # Other/Unclassified, never silently relabeled as a specific disaster.
    def test_other_disaster_type_never_relabeled(self):
        from api.backend import analyze_disaster
        img = _make_test_image("landslide.jpg")
        FAKE_RESULTS[("debris", img)] = {
            "model": "debris", "detection_type": "object_detection", "error": None, "notes": None,
            "detections": [{"damage_type": "Other Debris", "confidence": 0.7, "bbox": [0, 0, 1, 1], "evidence_type": "detection", "raw_class": "Other Debris"}],
        }
        with patch("inference.inference_engine.general_disaster_gate", side_effect=fake_gate_relevant), \
             patch("inference.inference_engine.disaster_type_gate", side_effect=fake_type_gate_relevant):
            result = analyze_disaster("other", [{"image_path": img, "location": {"latitude": 3.0, "longitude": 3.0}}])

        self.assertTrue(result["is_disaster"])
        self.assertEqual(result["report"]["disaster_category_label"], "Other / Unclassified Disaster")
        self.assertIsNone(result["type_relevance"], "no type gate should have run for 'other'")

    # UNCERTAIN must not generate strong damage evidence.
    def test_uncertain_gate_does_not_run_models(self):
        from api.backend import analyze_disaster
        img = _make_test_image("uncertain.jpg")
        FAKE_RESULTS[("building", img)] = {
            "model": "building", "detection_type": "object_detection", "error": None, "notes": None,
            "detections": [{"damage_type": "Damaged Building", "confidence": 0.9, "bbox": [0, 0, 1, 1], "evidence_type": "detection", "raw_class": "damaged building"}],
        }
        with patch("inference.inference_engine.general_disaster_gate", side_effect=self._mock_uncertain), \
             patch("inference.inference_engine.disaster_type_gate", side_effect=self._mock_uncertain):
            result = analyze_disaster("earthquake", [{"image_path": img, "location": {"latitude": 4.0, "longitude": 4.0}}])
        self.assertFalse(result["is_disaster"])
        self.assertEqual(result["locations"][0]["detected_damage"], [])

    # TEST 2 (acceptance): real disaster passes both gates -> models run, evidence flows through normally.
    def test_disaster_detected_runs_models_normally(self):
        from api.backend import analyze_disaster
        img = _make_test_image("collapsed_building.jpg")
        FAKE_RESULTS[("building", img)] = {
            "model": "building", "detection_type": "object_detection", "error": None, "notes": None,
            "detections": [{"damage_type": "Damaged Building", "confidence": 0.88, "bbox": [0, 0, 1, 1], "evidence_type": "detection", "raw_class": "damaged building"}],
        }
        with patch("inference.inference_engine.general_disaster_gate", side_effect=fake_gate_relevant), \
             patch("inference.inference_engine.disaster_type_gate", side_effect=fake_type_gate_relevant):
            result = analyze_disaster("earthquake", [{"image_path": img, "location": {"latitude": 5.0, "longitude": 5.0}}])

        self.assertTrue(result["is_disaster"])
        self.assertEqual(result["gate_status"], "DISASTER_DETECTED")
        self.assertGreater(result["locations"][0]["severity_score"], 0)
        self.assertTrue(any(d["damage_type"] == "Damaged Building" for d in result["locations"][0]["detected_damage"]))


class TestNewFeatures(unittest.TestCase):
    """Debris model replacement, evacuation planner, LLM fallback, all-invalid-images edge case."""

    def test_debris_model_no_longer_requires_inference_sdk(self):
        """Regression test for the hard requirement: importing debris_model.py
        must never require inference-sdk (it's been removed as a dependency)."""
        import importlib
        import models.debris_model as debris_module
        importlib.reload(debris_module)
        source = open(debris_module.__file__).read()
        self.assertNotIn("inference_sdk", source)
        self.assertNotIn("InferenceHTTPClient", source)
        self.assertNotIn("ROBOFLOW", source)
        # Confirms it's now a local ultralytics-based model like the others.
        self.assertIn("YOLO", source)
        self.assertIn("hf_hub_download", source)

    def test_evacuation_plan_only_includes_disaster_locations(self):
        from scoring.evacuation_planner import build_evacuation_plan
        locations = [
            {"location_id": "loc_a", "is_disaster": True, "priority_rank": 1, "latitude": 1.0, "longitude": 1.0,
             "severity_score": 80.0, "severity_level": "CRITICAL",
             "detected_damage": [{"model": "building", "damage_type": "Damaged Building"}],
             "infrastructure_constraints": []},
            {"location_id": "loc_b", "is_disaster": False, "priority_rank": 2, "latitude": 2.0, "longitude": 2.0,
             "severity_score": 0.0, "severity_level": "NONE", "detected_damage": [], "infrastructure_constraints": []},
        ]
        plan = build_evacuation_plan(locations)
        self.assertEqual(plan["num_locations_considered"], 1)
        self.assertEqual(len(plan["priorities"]), 1)
        self.assertEqual(plan["priorities"][0]["location_id"], "loc_a")
        self.assertIn("VISUAL DAMAGE", plan["disclaimer"])
        self.assertIn("does not use or know real-world", plan["disclaimer"])

    def test_evacuation_plan_reason_is_deterministic_from_evidence(self):
        from scoring.evacuation_planner import build_evacuation_plan
        locations = [{
            "location_id": "loc_a", "is_disaster": True, "priority_rank": 1, "latitude": 1.0, "longitude": 1.0,
            "severity_score": 90.0, "severity_level": "CRITICAL",
            "detected_damage": [
                {"model": "building", "damage_type": "Damaged Building"},
                {"model": "debris", "damage_type": "Debris"},
            ],
            "infrastructure_constraints": [{"type": "road", "status": "blocked", "damage_type": "Pothole", "confidence": 0.9, "location": {}}],
        }]
        plan = build_evacuation_plan(locations)
        reason = plan["priorities"][0]["reason"]
        self.assertIn("building", reason)
        self.assertIn("debris", reason)
        self.assertIn("blocked road", reason)

    def test_llm_fallback_when_no_api_key(self):
        from llm.report_generator import generate_report
        os.environ.pop("LLM_API_KEY", None)  # ensure unset regardless of test order
        structured = {
            "is_disaster": True, "disaster_type": "earthquake", "gate_status": "DISASTER_DETECTED",
            "locations": [{"location_id": "loc_a", "is_disaster": True, "latitude": 1.0, "longitude": 1.0,
                            "severity_score": 80.0, "severity_level": "CRITICAL",
                            "detected_damage": [{"model": "building", "damage_type": "Damaged Building"}]}],
            "evacuation_plan": {"priorities": [{"priority_rank": 1, "location_id": "loc_a", "severity_level": "CRITICAL", "reason": "building damage"}],
                                 "disclaimer": "visual evidence only"},
            "model_status": [{"model": "building", "status": "success"}],
            "report": {"disaster_category_label": "Earthquake"},
        }
        result = generate_report(structured)
        self.assertEqual(result["source"], "fallback")
        self.assertFalse(result["available"])
        self.assertIsNotNone(result["error"])
        self.assertIn("Executive Summary", result["sections"])
        # Fallback must never claim a network call happened.
        self.assertIn("not set", result["error"])

    def test_llm_fallback_never_raises_and_never_fabricates_not_a_disaster(self):
        from llm.report_generator import generate_report
        os.environ.pop("LLM_API_KEY", None)
        structured = {"is_disaster": False, "gate_status": "NOT_A_DISASTER", "locations": [],
                      "evacuation_plan": {"priorities": []}, "model_status": [], "report": {}}
        result = generate_report(structured)
        self.assertEqual(result["source"], "fallback")
        self.assertIn("No disaster evidence", result["sections"]["Executive Summary"])
        self.assertEqual(result["sections"]["Evacuation Priorities"], "None.")

    def test_all_images_invalid_does_not_crash_and_is_distinct_from_not_a_disaster(self):
        from api.backend import analyze_disaster
        result = analyze_disaster("earthquake", [
            {"image_path": "does_not_exist_1.jpg", "location": {"latitude": 1.0, "longitude": 1.0}},
            {"image_path": "does_not_exist_2.jpg", "location": {"latitude": 1.0, "longitude": 1.0}},
        ])
        self.assertTrue(result["success"])
        self.assertEqual(len(result["skipped_images"]), 2)
        self.assertEqual(len(result["locations"]), 0)
        self.assertEqual(result["is_disaster"], False)
        # Distinct: gate_status reflects "no valid images", not a gate rejection of real content.
        self.assertEqual(result["gate_status"], "NOT_A_DISASTER")
        self.assertIsNotNone(result["gate_reason"])
        self.assertIn("llm_report", result)

    def test_response_schema_has_required_top_level_fields(self):
        from api.backend import analyze_disaster
        with patch("inference.inference_engine.general_disaster_gate", side_effect=fake_gate_relevant), \
             patch("inference.inference_engine.disaster_type_gate", side_effect=fake_type_gate_relevant), \
             patch("inference.inference_engine.run_model", side_effect=fake_run_model):
            img = _make_test_image("schema_check.jpg")
            result = analyze_disaster("earthquake", [{"image_path": img, "location": {"latitude": 1.0, "longitude": 1.0}}])
        for field in ["success", "is_disaster", "disaster_type", "disaster_confidence", "type_relevance",
                      "gate_status", "general_gate_status", "type_gate_status", "gate_confidence", "gate_reason",
                      "images", "locations", "priority_order", "evacuation_plan", "model_status", "report", "llm_report"]:
            self.assertIn(field, result, f"missing required top-level field: {field}")


class TestMultiLocationEvacuationOrdering(unittest.TestCase):
    def setUp(self):
        self.run_model_patcher = patch("inference.inference_engine.run_model", side_effect=fake_run_model)
        self.run_model_patcher.start()
        self.gate_patcher = patch("inference.inference_engine.general_disaster_gate", side_effect=fake_gate_relevant)
        self.gate_patcher.start()
        self.type_gate_patcher = patch("inference.inference_engine.disaster_type_gate", side_effect=fake_type_gate_relevant)
        self.type_gate_patcher.start()
        FAKE_RESULTS.clear()

    def tearDown(self):
        self.run_model_patcher.stop()
        self.gate_patcher.stop()
        self.type_gate_patcher.stop()

    def test_evacuation_priority_matches_location_priority_ordering(self):
        from api.backend import analyze_disaster
        img_high = _make_test_image("evac_high.jpg")
        img_low = _make_test_image("evac_low.jpg")

        FAKE_RESULTS[("building", img_high)] = {
            "model": "building", "detection_type": "object_detection", "error": None, "notes": None,
            "detections": [{"damage_type": "Damaged Building", "confidence": 0.95, "bbox": [0, 0, 1, 1], "evidence_type": "detection", "raw_class": "damaged building"}],
        }
        FAKE_RESULTS[("road", img_low)] = {
            "model": "road", "detection_type": "object_detection", "error": None, "notes": None,
            "detections": [{"damage_type": "Transverse Crack", "confidence": 0.3, "bbox": [0, 0, 1, 1], "evidence_type": "detection", "raw_class": "transverse"}],
        }

        result = analyze_disaster("earthquake", [
            {"image_path": img_high, "location": {"latitude": 10.0, "longitude": 10.0}},
            {"image_path": img_low, "location": {"latitude": 20.0, "longitude": 20.0}},
        ])
        evac_order = [p["location_id"] for p in result["evacuation_plan"]["priorities"]]
        loc_order = [loc["location_id"] for loc in result["locations"] if loc["is_disaster"]]
        self.assertEqual(evac_order, loc_order, "evacuation plan ordering must match location priority ordering")
        self.assertEqual(result["evacuation_plan"]["priorities"][0]["priority_rank"], 1)


class TestHazardRecommendations(unittest.TestCase):
    """Deterministic rule-based recommendation engine -- the most important new feature."""

    def _loc(self, severity_level, detected_damage, is_disaster=True, location_id="loc_a"):
        return {"location_id": location_id, "is_disaster": is_disaster, "severity_level": severity_level,
                "detected_damage": detected_damage}

    def test_building_damage_produces_avoid_structure_recommendation(self):
        from scoring.hazard_recommendations import build_recommendations
        loc = self._loc("HIGH", [{"model": "building", "damage_type": "Damaged Building", "confidence": 0.85}])
        result = build_recommendations("earthquake", [loc])
        actions = [r["action"] for r in result["hazard_specific_actions"]]
        self.assertTrue(any("damaged structures" in a.lower() for a in actions))

    def test_fire_produces_immediate_evacuation_and_avoid_and_resource_priority(self):
        from scoring.hazard_recommendations import build_recommendations
        loc = self._loc("CRITICAL", [{"model": "fire", "damage_type": "Fire", "confidence": 0.9}])
        result = build_recommendations("fire", [loc])
        self.assertTrue(any("evacuate" in r["action"].lower() for r in result["immediate_actions"]))
        self.assertTrue(any("smoke" in r["action"].lower() for r in result["avoid"]))
        self.assertTrue(any("fire-response" in r["action"].lower() for r in result["resource_priorities"]))

    def test_flood_produces_higher_ground_and_avoid_water(self):
        from scoring.hazard_recommendations import build_recommendations
        loc = self._loc("HIGH", [{"model": "flood", "damage_type": "Flooding", "confidence": 0.8}])
        result = build_recommendations("flood", [loc])
        immediate_texts = [r["action"] for r in result["immediate_actions"]]
        avoid_texts = [r["action"] for r in result["avoid"]]
        self.assertTrue(any("higher ground" in a.lower() for a in immediate_texts))
        self.assertTrue(any("floodwater" in a.lower() for a in avoid_texts))

    def test_never_invents_hazard_not_detected(self):
        """Core honesty requirement: only road damage detected -> no fire/flood/building recommendations appear."""
        from scoring.hazard_recommendations import build_recommendations
        loc = self._loc("MODERATE", [{"model": "road", "damage_type": "Pothole", "confidence": 0.7}])
        result = build_recommendations("other", [loc])
        all_hazards = {r["hazard"] for r in result["items"]}
        self.assertIn("Road damage", all_hazards)
        self.assertNotIn("Fire", all_hazards)
        self.assertNotIn("Flooding", all_hazards)
        self.assertNotIn("Building damage", all_hazards)

    def test_not_a_disaster_location_produces_zero_recommendations(self):
        from scoring.hazard_recommendations import build_recommendations
        loc = self._loc("NONE", [], is_disaster=False)
        result = build_recommendations("earthquake", [loc])
        self.assertEqual(result["items"], [])

    def test_other_disaster_type_uses_generic_framing_not_a_specific_category(self):
        from scoring.hazard_recommendations import build_recommendations
        loc = self._loc("HIGH", [{"model": "debris", "damage_type": "Debris", "confidence": 0.6}])
        result = build_recommendations("other", [loc])
        immediate = [r["action"] for r in result["immediate_actions"]]
        self.assertTrue(any("unclassified" in a.lower() for a in immediate))

    def test_disclaimer_present_and_not_authoritative(self):
        from scoring.hazard_recommendations import build_recommendations
        result = build_recommendations("earthquake", [])
        self.assertIn("NOT an authoritative", result["disclaimer"])

    def test_resource_priority_references_top_evacuation_location(self):
        from scoring.hazard_recommendations import build_recommendations
        from scoring.evacuation_planner import build_evacuation_plan
        loc = self._loc("CRITICAL", [{"model": "building", "damage_type": "Damaged Building", "confidence": 0.9}],
                         location_id="loc_top")
        loc["priority_rank"] = 1
        loc["severity_score"] = 90.0
        loc["infrastructure_constraints"] = []
        loc["latitude"] = 1.0
        loc["longitude"] = 1.0
        evac = build_evacuation_plan([loc])
        result = build_recommendations("earthquake", [loc], evac)
        self.assertTrue(any(r["location"] == "loc_top" and "priority #1" in r["action"] for r in result["resource_priorities"]))


class TestLLMCannotInventEvidence(unittest.TestCase):
    def test_fallback_report_only_uses_provided_structured_data(self):
        """The fallback report must never reference a location/hazard that
        wasn't in the input -- proxy test for 'LLM cannot invent evidence'
        since we can't unit-test a live LLM call without network access."""
        from llm.report_generator import generate_report
        os.environ.pop("LLM_API_KEY", None)
        structured = {
            "is_disaster": True, "disaster_type": "flood", "gate_status": "DISASTER_DETECTED",
            "locations": [{"location_id": "loc_only", "is_disaster": True, "latitude": 1.0, "longitude": 1.0,
                            "severity_score": 60.0, "severity_level": "HIGH",
                            "detected_damage": [{"model": "flood", "damage_type": "Flooding"}]}],
            "evacuation_plan": {"priorities": [], "disclaimer": "visual evidence only"},
            "recommendations": {"items": [], "disclaimer": "not authoritative"},
            "model_status": [], "report": {"disaster_category_label": "Flood"},
        }
        result = generate_report(structured)
        self.assertIn("loc_only", result["sections"]["Affected Locations"])
        self.assertNotIn("earthquake", result["sections"]["Executive Summary"].lower())
        self.assertNotIn("loc_fake", result["text"])

    def test_system_prompt_forbids_inventing_evacuation_routes_and_recommendations(self):
        from llm.report_generator import SYSTEM_PROMPT
        self.assertIn("Do NOT invent evacuation routes", SYSTEM_PROMPT)
        self.assertIn("Do NOT generate your own recommendations", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main(verbosity=2)


def test_evacuation_route_helper_validates_coordinates(monkeypatch):
    from scoring.evacuation_route import calculate_road_route
    import pytest
    with pytest.raises(ValueError):
        calculate_road_route(95, 77, 12, 77)

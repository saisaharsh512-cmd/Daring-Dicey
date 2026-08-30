"""
llm/report_generator.py

Converts already-computed structured evidence into a human-readable incident
report. The LLM performs NO detection -- it only narrates what the gates,
models, and severity/evacuation engines already decided. It is explicitly
instructed never to invent detections, coordinates, severity, casualties,
population figures, hospital availability, road closures, or weather.

Configuration (environment variables, never hardcoded):
    LLM_API_KEY   -- if unset, this module NEVER attempts a network call and
                     always returns the deterministic fallback report. The
                     core analysis pipeline does not depend on this at all.
    LLM_MODEL     -- defaults to "claude-sonnet-4-5" (Anthropic Messages API).
                     Written for Anthropic's API by default; swap
                     `_call_llm()` if you use a different provider.

Returns a dict from generate_report() that is NEVER None and NEVER raises --
callers get {"source": "llm"|"fallback", "available": bool, "text": str,
"sections": {...}, "error": str|None} unconditionally.
"""
import logging
import os
from typing import Dict, Any

log = logging.getLogger("backend.llm.report_generator")

GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
GEMINI_MODEL_ENV = "GEMINI_MODEL"
DEFAULT_MODEL = "gemini-3.6-flash"

SECTION_NAMES = [
    "Executive Summary", "Disaster Assessment", "Affected Locations",
    "Severity Assessment", "Key Visual Evidence", "Model Confidence / Limitations",
    "Evacuation Priorities", "Recommended Immediate Actions", "Important Uncertainties",
]

SYSTEM_PROMPT = """You write a disaster-response incident report from structured JSON evidence only.

STRICT RULES:
- Use ONLY the facts present in the JSON provided. Do not invent detections, coordinates,
  severity scores, casualties, population figures, hospital availability, road closures,
  or weather conditions.
- Do NOT invent evacuation routes. The JSON's evacuation_plan and recommendations reflect
  visual-evidence-based priority only, not verified real-world routing -- present them as such.
- Do NOT generate your own recommendations. The JSON's "recommendations" field is the
  authoritative, deterministic, rule-based recommendation set. Narrate and organize it;
  do not add new recommendations beyond what it contains.
- If information needed for a section is not in the JSON, explicitly say it is unavailable
  or unknown -- do not guess or estimate.
- The evacuation priority ordering reflects VISUAL damage evidence only, not real-world
  routing, population density, or infrastructure capacity -- state this limitation clearly
  wherever evacuation priorities are discussed.
- For "Other/Unclassified Disaster" cases, you may describe likely characteristics based on
  the visible evidence, but you MUST clearly distinguish inference ("this may suggest...")
  from certainty ("this is...").
- Never claim a road, building, or area is "safe" -- only report what was or wasn't detected.
- Clearly distinguish AI detection (what a model saw), AI recommendation (what the rule
  engine suggests), and uncertainty (what the system could not determine).

Write the report with exactly these section headings, in this order:
Executive Summary, Disaster Assessment, Affected Locations, Severity Assessment,
Key Visual Evidence, Model Confidence / Limitations, Evacuation Priorities,
Recommended Immediate Actions, Important Uncertainties.

Keep it concise -- a few sentences to a short paragraph per section."""


def _build_fallback_report(structured_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Deterministic, template-based report built directly from structured data,
    with zero network dependency. This is what the app uses when LLM_API_KEY
    is unset or the LLM call fails -- the core analysis never depends on the
    LLM being available.
    """
    is_disaster = structured_data.get("is_disaster", False)
    disaster_type = structured_data.get("disaster_type", "unknown")
    locations = structured_data.get("locations", [])
    evac = structured_data.get("evacuation_plan", {})
    model_status = structured_data.get("model_status", [])

    if not is_disaster:
        return {
            "Executive Summary": "No disaster evidence was detected in the submitted image(s). "
                                  "The relevance gate did not classify this input as disaster-related.",
            "Disaster Assessment": f"Not applicable -- gate status: {structured_data.get('gate_status', 'unknown')}.",
            "Affected Locations": "None.",
            "Severity Assessment": "Severity is 0 / not applicable -- no disaster was confirmed.",
            "Key Visual Evidence": "None -- specialized damage models were not run.",
            "Model Confidence / Limitations": "Relevance gates use CLIP zero-shot classification, a heuristic "
                                               "check, not a certified disaster classifier.",
            "Evacuation Priorities": "None.",
            "Recommended Immediate Actions": "None required based on this submission.",
            "Important Uncertainties": "If this classification seems wrong, re-submit with a clearer "
                                        "disaster-related image or verify manually.",
        }

    disaster_locs = [l for l in locations if l.get("is_disaster")]
    affected = "; ".join(
        f"{l['location_id']} ({l['latitude']:.4f}, {l['longitude']:.4f}) -- {l['severity_level']}"
        for l in disaster_locs
    ) or "None."

    evidence_lines = []
    for l in disaster_locs:
        types = sorted(set(d["damage_type"] for d in l["detected_damage"]))
        if types:
            evidence_lines.append(f"{l['location_id']}: {', '.join(types)}")
    evidence_text = "; ".join(evidence_lines) or "No specific damage types recorded."

    model_lines = [f"{m['model']}: {m['status']}" for m in model_status]

    evac_lines = [f"#{p['priority_rank']} {p['location_id']} ({p['severity_level']}) -- {p['reason']}"
                  for p in evac.get("priorities", [])]

    recs = structured_data.get("recommendations", {})
    rec_lines = [f"[{r['priority']}] {r['action']} ({r['hazard']} at {r['location']})" for r in recs.get("items", [])]

    return {
        "Executive Summary": f"Disaster detected. Selected type: {disaster_type}. "
                              f"{len(disaster_locs)} location(s) with confirmed evidence.",
        "Disaster Assessment": f"Classified as: {structured_data.get('report', {}).get('disaster_category_label', disaster_type)}. "
                                f"Gate status: {structured_data.get('gate_status', 'unknown')}.",
        "Affected Locations": affected,
        "Severity Assessment": "; ".join(f"{l['location_id']}: {l['severity_score']}/100 ({l['severity_level']})" for l in disaster_locs) or "N/A",
        "Key Visual Evidence": evidence_text,
        "Model Confidence / Limitations": "; ".join(model_lines) or "No model status available.",
        "Evacuation Priorities": ("; ".join(evac_lines) or "None computed.") + " " + evac.get("disclaimer", ""),
        "Recommended Immediate Actions": ("; ".join(rec_lines) or "None generated.") + " " + recs.get("disclaimer", ""),
        "Important Uncertainties": "This report is generated from AI visual detection only. It does not include "
                                    "real casualty counts, population data, hospital capacity, or verified road status.",
    }


def _call_llm(structured_data: Dict[str, Any], api_key: str, model: str) -> str:
    """Generate the incident report using Google's Gemini API."""
    import json
    from google import genai

    client = genai.Client(api_key=api_key)

    prompt = f"""
{SYSTEM_PROMPT}

Here is the structured disaster-analysis JSON:

{json.dumps(structured_data, default=str, indent=2)}

Generate the incident report now using ONLY the information above.
"""

    response = client.models.generate_content(
        model=model,
        contents=prompt,
    )

    if not response.text:
        raise RuntimeError("Gemini response contained no text")

    return response.text


def generate_report(structured_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Never raises. Always returns:
      {"source": "llm"|"fallback", "available": bool, "text": str,
       "sections": {name: text} or None, "error": str|None}
    """
    api_key = os.environ.get(GEMINI_API_KEY_ENV)

    if not api_key:
        log.info("[LLM] %s not set -- using deterministic fallback report", GEMINI_API_KEY_ENV)
        sections = _build_fallback_report(structured_data)
        return {
            "source": "fallback", "available": False,
            "text": "\n\n".join(f"## {k}\n{v}" for k, v in sections.items()),
            "sections": sections,
            "error": f"{GEMINI_API_KEY_ENV} not set -- LLM report unavailable, showing deterministic fallback.",
        }

    model = os.environ.get(GEMINI_MODEL_ENV, DEFAULT_MODEL)
    try:
        log.info("[LLM] Generating report via %s...", model)
        text = _call_llm(structured_data, api_key, model)
        return {"source": "llm", "available": True, "text": text, "sections": None, "error": None}
    except Exception as e:
        log.warning("[LLM] call failed (%s) -- falling back to deterministic report", e)
        sections = _build_fallback_report(structured_data)
        return {
            "source": "fallback", "available": False,
            "text": "\n\n".join(f"## {k}\n{v}" for k, v in sections.items()),
            "sections": sections,
            "error": f"LLM call failed: {e}. Showing deterministic fallback report.",
        }

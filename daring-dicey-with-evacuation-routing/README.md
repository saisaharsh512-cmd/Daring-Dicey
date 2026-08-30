# Disaster Response AI

A dashboard that takes photos from a disaster site, figures out what's actually going on in them, and turns that into something a rescue team can use: which locations are worst hit, what order to hit them in, and how to actually get there.

Built for [Hackathon Name] by [Team Name].

## The problem we're actually solving

After a disaster, the first photos coming in are usually a mess — people uploading whatever they can from wherever they are, no structure, no way to tell at a glance which ones show something serious versus a blurry photo of nothing. Responders end up scrolling through a pile of images trying to triage manually.

We wanted something that takes that pile of images + rough locations and spits out: is this actually a disaster, how bad is each spot, where do you send help first, and what's the smartest way to get a team there if a road is out.

We are **not** claiming this replaces real emergency services or gives verified routing/safety data. It's a triage and decision-support tool built on computer vision models and OpenStreetMap data. Every screen in the app is upfront about that, and so is this README.

## What it actually does

### 1. It checks if an image is even relevant before doing anything else

This was the first big bug we had to design around: if you upload a photo of a burger and select "Earthquake," a naive pipeline will still run the building-damage model on it, and if that model hallucinates a detection, you get a fake "damaged building" result out of a food photo. That's obviously bad for a tool that's supposed to help triage.

So every image goes through two gates before any specialized model touches it:

- **General relevance gate** — is this even disaster-related? (CLIP zero-shot, comparing the image against disaster-scene prompts vs. everyday-scene prompts)
- **Disaster-type gate** — if it's disaster-related, does it actually match the disaster type the user selected? (Earthquake photo selected as "Flood" gets rejected here)

Both gates return `RELEVANT`, `NOT_RELEVANT`, or `UNCERTAIN`. Specialized models only run if both gates say `RELEVANT`. `UNCERTAIN` is treated conservatively — no models run, but it's shown as a distinct state, not lumped in with "not a disaster."

Selecting "Other / Unclassified" skips the type-specific gate entirely and never gets silently relabeled as one of the named disaster types.

### 2. Six specialized models, each doing one job

We didn't want one model pretending to detect everything. Each of these only runs when the gates say it's relevant to the selected disaster type:

| Model | What it does | Real talk about its limits |
|---|---|---|
| **Earthquake** | CLIP zero-shot scene classification + grid-tile regional evidence | This is a heuristic, not a trained detector. We say so explicitly in the output (`evidence_type: "regional_evidence"`) rather than pretending it's the same as a real bounding-box model |
| **Building damage** | YOLOv10 object detector | Binary — damaged vs. undamaged. No "minor/major/collapsed" gradation, because the model we're using doesn't have those classes |
| **Road damage** | YOLOv8 object detector | 7 classes (pothole, alligator crack, etc.). No "repaired road" class exists in this checkpoint, so it can't recognize a road that's already been fixed |
| **Fire / Smoke** | YOLOv8 object detector | Straightforward fire + smoke detection |
| **Debris** | YOLOv8 segmentation model (reuses the same RescueNet checkpoint as the building model, different weights file) | Originally this used a remote Roboflow API that kept failing — replaced with a fully local model, no external API dependency, no API key needed |
| **Flood** | Image classifier | Whole-image only — no bounding boxes, no localization within the frame |

The router only runs models actually relevant to the selected disaster (e.g. earthquake doesn't bother running the flood model), so you're not wasting inference time on models that can't produce useful evidence anyway.

**If a model fails or is unavailable, the app says so.** It never shows "0 detections" for a model that didn't run — there's a real difference between "we checked and found nothing" and "we couldn't check," and the UI keeps them separate everywhere (Model Status page, per-location cards, the incident report).

### 3. Severity scoring that isn't just "highest confidence wins"

A model being 95% confident about a hairline crack shouldn't outrank a model being 70% confident about a collapsed building. So severity is computed from:

- what type of damage was found (a pothole and a building collapse are not the same severity, regardless of confidence)
- how many detections, and how much area they cover
- confidence, but only as a secondary multiplier — never the deciding factor

Locations get bucketed into LOW / MODERATE / HIGH / CRITICAL, and multiple images at roughly the same GPS coordinates (configurable clustering radius) get merged into one location instead of double-counting the same spot.

### 4. Evacuation priority + rule-based recommendations

Once locations are scored, they get ranked by priority — highest severity first, with deterministic tie-breaking rules (never random ordering). Alongside that, a rule-based recommendation engine generates hazard-specific action items: fire detected → evacuate + avoid smoke-affected areas; flooding detected → move to higher ground + avoid submerged roads; road damage → avoid the segment, use alternate access; and so on per disaster type.

This is a plain if/then rule engine, not an LLM guessing at recommendations — we wanted the "why" behind every suggestion to be traceable back to an actual detection, not vibes from a language model.

### 5. Rescue team allocation

Tell it how many teams you've got, and it distributes them across the affected locations by priority — highest-severity locations get covered first, and if you've got more teams than locations, the extras get distributed proportionally to severity (using the largest-remainder method, so the numbers actually add up to what you typed in, not some rounded approximation).

### 6. An interactive map that's actually the centerpiece, not an afterthought

- Click an uploaded image, click the map, that's its location — no typing coordinates
- **Search bar** (top-left, Nominatim/OpenStreetMap — free, no API key) to jump to a place by name instead of hunting around the map
- Severity-colored markers with priority badges once analysis is done
- **Safe zone marker** — mark your team's staging area, and the optimal route calculation starts from there
- **Optimal route tab** — real road-network routing (OSRM, also free/no-key) connecting locations in priority order, drawn highlighted on the map like turn-by-turn directions. If a location has road damage evidence, the route tries an alternate path instead of the default fastest one — though we're upfront that this is a best-effort heuristic (we know a location has reported road damage, we don't know the exact damaged segment's GPS geometry, so "avoid the damaged road" really means "prefer a different real road out of that area")

One map instance for the entire session — it doesn't get torn down and rebuilt every time you switch tabs. That sounds like a small thing but it was actually the most annoying bug to track down (see "Things that broke and how we fixed them" below if you're curious).

### 7. Incident report, AI-assisted but not AI-authoritative

The report pulls together everything — severity, locations, hazards, evacuation priority, recommendations, model status — and hands it to Gemini to write up as a readable summary. If there's no API key configured, or the call fails for any reason, it falls back to a plain template-based report built from the same structured data. Either way the app works; the LLM is a nice-to-have on top of data that's already fully computed without it.

The report explicitly separates "detected by a model" from "recommended by the rule engine" from "written up by the LLM" — the LLM never gets to invent a detection, a coordinate, or a severity number, only narrate what's already there.

Exportable as an actual PDF, not just plain text.

## Tech stack

**Frontend:** React 19 + Vite, Leaflet / react-leaflet for the map, vanilla CSS (no UI framework), jsPDF for report export, Vitest for testing.

**Backend:** FastAPI, Ultralytics YOLO (v8/v10) for the object detectors, Hugging Face Transformers for the flood classifier and CLIP, Google Gemini for the incident report narrative.

Nothing here requires a paid API key except Gemini, and even that's optional — the app is fully functional without it.

## Running it

```bash
# backend
cd backend
pip install -r requirements.txt
export GEMINI_API_KEY=your_key   # optional — app works without it
uvicorn api.server:app --reload --port 8000

# frontend
cd frontend
npm install
npm run dev
```

Backend runs on `:8000`, frontend dev server proxies to it. First model load takes a bit (downloading weights); after that it's cached.

## Testing

```bash
# backend
cd backend && python -m unittest tests.test_backend -v

# frontend
cd frontend
npm run build   # production build
npm run lint    # oxlint
npm test        # vitest — includes a regression test that specifically checks
                 # the map mounts exactly once across tab switches, since that
                 # was the bug we spent the most time on
```

## Things that broke and how we fixed them

Worth mentioning because it's genuinely where most of the debugging time went:

**The map kept going black / laggy when switching tabs.** Turned out to be two separate issues stacked on top of each other. First, Leaflet's own CSS file wasn't being imported anywhere — without it, the map's internal panes have no positioning rules to work with, so tiles render in the wrong place or don't render at all. Second, our tab-switching logic was straight-up unmounting and remounting the whole map component every time you left the Map tab, which meant Leaflet was tearing down and rebuilding its entire internal state constantly. Fixed by keeping exactly one map instance alive for the whole session (hidden via CSS `display:none` when you're on another tab, not removed from the DOM) and calling `map.invalidateSize()` at the right moment when it becomes visible again.

**Search box clicks were moving map markers.** Clicking into the search bar was bubbling through to the map underneath and getting interpreted as "user clicked here, place a marker." React's built-in event handling doesn't actually stop this reliably because of how it delegates events — had to use Leaflet's own `L.DomEvent.disableClickPropagation()`, which is the tool actually built for this exact situation.

**Debris detection depended on a flaky third-party API.** Originally used a remote Roboflow endpoint that kept timing out. Swapped it for a fully local YOLO segmentation model — no network dependency, no API key, no more random failures.

## Known limitations (we'd rather tell you than have you find out)

#Demo video link - https://drive.google.com/file/d/1mnUKQ9jt7vviCBewsifDZS5rTD_OCRfJ/view?usp=drivesdk #

- None of the vision models are independently benchmarked for accuracy on this specific use case — they're solid pretrained/fine-tuned models, but we haven't validated them against a labeled disaster dataset
- The earthquake "model" is a CLIP zero-shot heuristic, not a purpose-trained detector — it's the weakest link in the detection chain and we say so in the UI
- Road-damage avoidance in routing is best-effort, not guaranteed — we don't have segment-level GPS data for exactly which stretch of road is damaged
- Building damage detection is binary (damaged/undamaged) with no severity gradation
- Rescue team allocation and evacuation priority are based purely on visual evidence — no real population density, hospital capacity, or road-closure data feeds into it
- This is a prototype, not a certified emergency response tool. Treat every output as a starting point for a human decision, not the decision itself

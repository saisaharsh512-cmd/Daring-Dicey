// api.js
//
// Every call in this file talks to the existing backend. Nothing here
// computes severity, ranks locations, or invents damage categories --
// it only shapes the HTTP request and returns exactly what the backend
// sent back.

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const FALLBACK_DISASTER_TYPES = [
  { value: "earthquake", models_run: [] },
  { value: "flood", models_run: [] },
  { value: "wildfire", models_run: [] },
  { value: "cyclone", models_run: [] },
  { value: "landslide", models_run: [] },
  { value: "other", models_run: [] },
];

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/health`, { signal: AbortSignal.timeout(4000) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchDisasterTypes() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/disaster-types`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error("bad response");
    const data = await res.json();
    if (Array.isArray(data.disaster_types) && data.disaster_types.length > 0) {
      return data.disaster_types;
    }
    return FALLBACK_DISASTER_TYPES;
  } catch {
    // Backend not reachable yet -- fall back to the four types documented
    // in the backend's own README, so the dropdown still works, but this
    // is display-only and never affects scoring.
    return FALLBACK_DISASTER_TYPES;
  }
}

/**
 * queueItems: [{ id, file, latitude, longitude }]
 * Sends images + parallel locations array + disaster_type to POST /api/analyze.
 * Returns the backend's response JSON verbatim (plus the wrapper's
 * image_id_map field), or throws ApiError with a useful message.
 */
export async function analyzeDisaster(disasterType, queueItems, clusterToleranceMeters, totalRescueMembers = 0) {
  const formData = new FormData();
  formData.append("disaster_type", disasterType);
  formData.append("total_rescue_members", String(Math.max(0, Number(totalRescueMembers) || 0)));
  if (clusterToleranceMeters !== undefined) {
    formData.append("cluster_tolerance_meters", String(clusterToleranceMeters));
  }

  const locations = queueItems.map((item) => {
    const lat = parseFloat(item.latitude);
    const lng = parseFloat(item.longitude);
    if (Number.isNaN(lat) || Number.isNaN(lng)) return null;
    return { latitude: lat, longitude: lng };
  });
  formData.append("locations", JSON.stringify(locations));

  for (const item of queueItems) {
    formData.append("images", item.file, item.file.name);
  }

  let res;
  try {
    res = await fetch(`${API_BASE_URL}/api/analyze`, {
      method: "POST",
      body: formData,
      signal: AbortSignal.timeout(180000), // model inference can be slow, especially first-load / remote debris calls
    });
  } catch (err) {
    throw new ApiError(
      `Could not reach the backend at ${API_BASE_URL}. Is it running? (${err.message})`,
      0
    );
  }

  let body;
  try {
    body = await res.json();
  } catch {
    throw new ApiError(`Backend returned an unreadable response (HTTP ${res.status}).`, res.status);
  }

  if (!res.ok) {
    throw new ApiError(body?.detail || `Backend error (HTTP ${res.status})`, res.status);
  }

  return body;
}


export async function calculateEvacuationRoute({
  origin_latitude,
  origin_longitude,
  destination_latitude,
  destination_longitude,
  destination_name,
}) {
  let res;
  try {
    res = await fetch(`${API_BASE_URL}/api/evacuation-route`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origin_latitude,
        origin_longitude,
        destination_latitude,
        destination_longitude,
        destination_name,
      }),
      signal: AbortSignal.timeout(30000),
    });
  } catch (err) {
    throw new ApiError(`Could not reach the backend at ${API_BASE_URL}. (${err.message})`, 0);
  }

  let body;
  try { body = await res.json(); }
  catch { throw new ApiError(`Backend returned an unreadable response (HTTP ${res.status}).`, res.status); }
  if (!res.ok) throw new ApiError(body?.detail || `Route calculation failed (HTTP ${res.status})`, res.status);
  return body;
}

export { API_BASE_URL };

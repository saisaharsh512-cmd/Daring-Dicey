import { useMemo, useState, useCallback } from "react";
import LocationMap from "./LocationMap";

/**
 * Single persistent map used for the whole session: location-assignment
 * mode before analysis, severity-colored results mode after. The
 * `<LocationMap>` element below is ALWAYS rendered -- never conditionally
 * removed from the tree -- so exactly one Leaflet instance exists for the
 * app's lifetime. The "nothing to show yet" message is an overlay on top
 * of the (still-mounted, still-rendering-the-default-view) map, not a
 * replacement for it.
 */
export default function MapPanel({ queue, activeImageId, onMapClick, result, visible = true }) {
  const [fitSignal, setFitSignal] = useState(0);
  const locatedCount = queue.filter((q) => q.latitude !== "" && q.longitude !== "").length;
  const isEmpty = queue.length === 0 && !result;

  const assignmentMarkers = useMemo(
    () =>
      queue
        .filter((q) => q.latitude !== "" && q.longitude !== "")
        .map((q) => ({ id: q.id, latitude: Number(q.latitude), longitude: Number(q.longitude), label: q.file.name })),
    [queue]
  );

  const resultMarkers = useMemo(() => {
    if (!result) return [];
    return result.locations.map((loc) => {
      const severity = loc.is_disaster
        ? loc.severity_level
        : loc.gate_status?.startsWith("UNCERTAIN")
          ? "UNCERTAIN"
          : "NOT_DISASTER";
      const hazards = Array.from(new Set((loc.detected_damage || []).map((d) => d.damage_type)));
      const evac = result.evacuation_plan?.priorities?.find((p) => p.location_id === loc.location_id);
      return {
        id: loc.location_id,
        latitude: loc.latitude,
        longitude: loc.longitude,
        label: loc.location_id.replace("_", " "),
        severity,
        priorityRank: loc.is_disaster ? loc.priority_rank : null,
        numImages: loc.num_images,
        hazards,
        recommendedAction: evac?.reason,
      };
    });
  }, [result]);

  const handleMarkerClick = useCallback((locationId) => {
    document.getElementById(locationId)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  const handleFitAll = useCallback(() => setFitSignal((s) => s + 1), []);

  return (
    <section className="panel map-panel">
      {!result && !isEmpty && (
        <>
          <div className="map-panel__header">
            <h2>Location</h2>
            <div className="map-panel__header-actions">
              <span className="mono map-panel__count">{locatedCount}/{queue.length} located</span>
              <button type="button" className="map-panel__fit-btn" onClick={handleFitAll}>Reset / Fit All</button>
            </div>
          </div>
          <ul className="map-panel__status-chips">
            {queue.map((item, i) => (
              <li key={item.id} className={`status-chip ${item.latitude !== "" ? "status-chip--located" : "status-chip--pending"}`}>
                Image {i + 1} → {item.latitude !== "" ? "Located" : "Not located"}
              </li>
            ))}
          </ul>
          <p className="field-hint">
            {activeImageId ? "Click the map to place the selected image." : "Select an image, then click the map."}
          </p>
        </>
      )}
      {result && (
        <div className="map-panel__header">
          <h2>Location Results</h2>
          <div className="map-panel__header-actions">
            <span className="mono map-panel__count">{result.locations.length} location{result.locations.length === 1 ? "" : "s"}</span>
            <button type="button" className="map-panel__fit-btn" onClick={handleFitAll}>Reset / Fit All</button>
          </div>
        </div>
      )}

      <div className="map-panel__map-wrapper">
        {isEmpty && (
          <div className="map-panel__overlay">
            <span className="map-panel__empty-icon">🗺️</span>
            <p>Upload images to start placing them on the map.</p>
          </div>
        )}
        <LocationMap
          markers={result ? resultMarkers : assignmentMarkers}
          activeMarkerId={result ? null : activeImageId}
          onMapClick={result ? null : onMapClick}
          onMarkerClick={result ? handleMarkerClick : null}
          readOnly={!!result}
          visible={visible}
          fitSignal={fitSignal}
        />
      </div>
    </section>
  );
}

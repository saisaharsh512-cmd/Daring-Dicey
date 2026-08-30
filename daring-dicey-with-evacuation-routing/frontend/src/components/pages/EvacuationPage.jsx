import { useMemo, useState } from "react";
import { calculateEvacuationRoute } from "../../api";
import { severityMeta } from "../../severity";
import EvacuationRouteMap from "../EvacuationRouteMap";

export default function EvacuationPage({ result }) {
  const priorities = result?.evacuation_plan?.priorities || [];
  const [locationId, setLocationId] = useState(priorities[0]?.location_id || "");
  const [safeName, setSafeName] = useState("Emergency Safe Zone");
  const [safeLat, setSafeLat] = useState("");
  const [safeLng, setSafeLng] = useState("");
  const [route, setRoute] = useState(null);
  const [loading, setLoading] = useState(false);
  const [routeError, setRouteError] = useState(null);

  const selected = useMemo(
    () => result?.locations?.find((loc) => loc.location_id === locationId),
    [result, locationId]
  );

  if (!result) {
    return <div className="page"><div className="panel empty-panel"><p>Run an analysis to configure evacuation routing.</p></div></div>;
  }

  if (!result.is_disaster || priorities.length === 0) {
    return <div className="page"><div className="panel"><p className="empty-note">No evacuation route can be planned because there are no disaster-confirmed locations.</p></div></div>;
  }

  const calculate = async (event) => {
    event.preventDefault();
    setRouteError(null);
    setRoute(null);
    if (!selected) return setRouteError("Select an affected location.");
    if (safeLat === "" || safeLng === "") return setRouteError("Enter the safe-zone latitude and longitude.");

    setLoading(true);
    try {
      const data = await calculateEvacuationRoute({
        origin_latitude: selected.latitude,
        origin_longitude: selected.longitude,
        destination_latitude: safeLat,
        destination_longitude: safeLng,
        destination_name: safeName,
      });
      setRoute(data);
    } catch (err) {
      setRouteError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <section className="panel">
        <div className="panel__title">
          <h2>Evacuation Routing</h2>
          <p className="disclaimer-note">
            Select an affected location and enter a responder-verified safe-zone coordinate. The system calculates a road-network route; it does not know live closures or guarantee safety.
          </p>
        </div>

        <form className="route-form" onSubmit={calculate}>
          <label>
            Affected location
            <select value={locationId} onChange={(e) => setLocationId(e.target.value)}>
              {priorities.map((p) => (
                <option key={p.location_id} value={p.location_id}>
                  #{p.priority_rank} · {p.location_id.replaceAll("_", " ")} · {p.severity_level}
                </option>
              ))}
            </select>
          </label>
          <label>
            Safe zone / shelter name
            <input value={safeName} onChange={(e) => setSafeName(e.target.value)} placeholder="Emergency Shelter A" />
          </label>
          <div className="route-form__grid">
            <label>Safe-zone latitude<input value={safeLat} onChange={(e) => setSafeLat(e.target.value)} placeholder="12.971600" inputMode="decimal" /></label>
            <label>Safe-zone longitude<input value={safeLng} onChange={(e) => setSafeLng(e.target.value)} placeholder="77.594600" inputMode="decimal" /></label>
          </div>
          <button type="submit" className="route-form__button" disabled={loading}>
            {loading ? "CALCULATING ROUTE…" : "CALCULATE EVACUATION ROUTE"}
          </button>
          {routeError && <p className="route-form__error">{routeError}</p>}
        </form>
      </section>

      <section className="panel">
        <div className="panel__title">
          <h2>Evacuation Priority</h2>
          <p className="disclaimer-note">{result.evacuation_plan.disclaimer}</p>
        </div>
        <div className="evac-detail-list">
          {priorities.map((p) => {
            const meta = severityMeta(p.severity_level);
            return (
              <article key={p.location_id} className="evac-detail-card" style={{ "--rung-color": meta.color }}>
                <div className="evac-detail-card__rank mono" style={{ color: meta.color }}>#{p.priority_rank}</div>
                <div className="evac-detail-card__body">
                  <div className="evac-detail-card__title"><span>{p.location_id.replaceAll("_", " ")}</span><span className="mono" style={{ color: meta.color }}>{meta.label}</span></div>
                  <div className="evac-detail-card__why"><h4>Why this location is prioritized</h4><p>{p.reason}</p></div>
                  <p className="evac-detail-card__action">Coordinates: {p.latitude.toFixed(5)}, {p.longitude.toFixed(5)}</p>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      {route && (
        <section className="panel route-result">
          <div className="panel__title"><h2>Recommended Road Route</h2><p>{route.disclaimer}</p></div>
          <div className="route-stats">
            <div><span>ORIGIN</span><strong>{selected?.location_id?.replaceAll("_", " ")}</strong></div>
            <div><span>DESTINATION</span><strong>{route.destination.name}</strong></div>
            <div><span>DISTANCE</span><strong>{route.distance_km} km</strong></div>
            <div><span>EST. DRIVE TIME</span><strong>{route.duration_minutes} min</strong></div>
          </div>
          <EvacuationRouteMap route={route} />
          <p className="route-provider">Routing provider: {route.provider}. Confirm road conditions locally before directing civilians.</p>
        </section>
      )}
    </div>
  );
}

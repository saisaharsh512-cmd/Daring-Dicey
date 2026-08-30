import { MapContainer, TileLayer, Marker, Popup, ZoomControl, useMapEvents, useMap } from "react-leaflet";
import { memo, useMemo, useRef, useEffect } from "react";
import L from "leaflet";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
import { severityMeta } from "../severity";
import LocationSearch from "./LocationSearch";

// react-leaflet's default marker icon path breaks under Vite's asset bundling
// unless explicitly re-pointed at the bundled asset URLs.
L.Marker.prototype.options.icon = L.icon({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});

const DEFAULT_CENTER = [20.5937, 78.9629]; // India, roughly -- just a reasonable default view, not tied to any real location
const DEFAULT_ZOOM = 5;

function buildDotIcon(color, { active = false, label = null } = {}) {
  const size = active ? 26 : 20;
  const badge = label ? `<span class="map-pin__badge">${label}</span>` : "";
  return L.divIcon({
    className: "map-pin-wrapper",
    html: `<span class="map-pin ${active ? "map-pin--active" : ""}" style="background:${color};width:${size}px;height:${size}px;">${badge}</span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

// Cache icons by (severity, active, label) so identical markers reuse the same
// L.DivIcon instance across renders instead of rebuilding it every time.
const iconCache = new Map();
function getIcon(severity, active, label) {
  const key = `${severity}|${active}|${label ?? ""}`;
  if (!iconCache.has(key)) {
    iconCache.set(key, buildDotIcon(severityMeta(severity).color, { active, label }));
  }
  return iconCache.get(key);
}

function ClickHandler({ onMapClick }) {
  useMapEvents({
    click(e) {
      onMapClick({ latitude: e.latlng.lat, longitude: e.latlng.lng });
    },
  });
  return null;
}

// Fits map bounds to markers exactly ONCE per "initial load" transition
// (0 markers -> some markers), plus whenever fitSignal changes (the
// explicit Reset/Fit All button) -- never on every incremental marker edit.
// Reads current positions via a ref (updated every render, not a reactive
// dependency) so the effect's dependency array can stay simple and complete.
function FitBounds({ positions, fitSignal }) {
  const map = useMap();
  const positionsRef = useRef(positions);
  const hasFittedInitially = useRef(false);
  const lastFitSignal = useRef(fitSignal);
  const hasPositions = positions.length > 0;

  // Keeps positionsRef fresh as a post-render side effect (never mutates a
  // ref during render itself). Runs after every render -- cheap, just an
  // assignment -- and always completes before the effect below (React runs
  // a component's effects in declaration order on each commit).
  useEffect(() => {
    positionsRef.current = positions;
  });

  useEffect(() => {
    const manualTrigger = fitSignal !== lastFitSignal.current;
    lastFitSignal.current = fitSignal;

    const pts = positionsRef.current;
    if (pts.length === 0) return;

    if (!hasFittedInitially.current || manualTrigger) {
      hasFittedInitially.current = true;
      if (pts.length === 1) {
        map.setView(pts[0], 14);
      } else {
        map.fitBounds(pts, { padding: [40, 40] });
      }
    }
  }, [hasPositions, fitSignal, map]);

  return null;
}

// THE map-visibility fix: when this map is inside a CSS-hidden (display:none)
// tab that becomes visible again, Leaflet's cached internal pixel dimensions
// are stale (computed against a 0x0 or pre-hide container) and tiles render
// incorrectly/blank until invalidateSize() runs -- but only AFTER the browser
// has actually completed the layout reflow from the display change. A single
// requestAnimationFrame can fire before layout settles in some browsers, so
// this uses a double-rAF, the standard robust pattern. Never fires on every
// render -- only on the false->true edge of `visible`.
function VisibilitySync({ visible }) {
  const map = useMap();
  const wasVisible = useRef(visible);

  useEffect(() => {
    if (visible && !wasVisible.current) {
      let raf2;
      const raf1 = requestAnimationFrame(() => {
        raf2 = requestAnimationFrame(() => map.invalidateSize());
      });
      wasVisible.current = true;
      return () => {
        cancelAnimationFrame(raf1);
        if (raf2) cancelAnimationFrame(raf2);
      };
    }
    wasVisible.current = visible;
  }, [visible, map]);

  return null;
}

/**
 * markers: [{ id, latitude, longitude, label, severity?, priorityRank?, hazards?, numImages?, recommendedAction? }]
 * activeMarkerId: which marker is "selected" for map-click placement (assignment mode).
 * onMapClick: null in read-only (post-analysis) mode -- clicking does nothing.
 * onMarkerClick(id): called when a marker itself is clicked.
 * visible: whether this map's tab/container is currently on-screen. Drives
 *          the invalidateSize fix -- has NO effect on mount/unmount.
 * fitSignal: bump this (any changing value) to trigger an explicit re-fit
 *            (the "Reset / Fit All" button), independent of the one-time
 *            automatic initial fit.
 */
function LocationMap({ markers, activeMarkerId, onMapClick, onMarkerClick, readOnly = false, visible = true, fitSignal = 0 }) {
  const positions = useMemo(() => markers.map((m) => [m.latitude, m.longitude]), [markers]);

  return (
    <div className="location-map">
      <MapContainer center={DEFAULT_CENTER} zoom={DEFAULT_ZOOM} scrollWheelZoom style={{ height: "100%", width: "100%" }} zoomControl={false}>
        <ZoomControl position="topright" />
        <LocationSearch onMapClick={onMapClick} />
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          updateWhenZooming={false}
          keepBuffer={2}
          eventHandlers={{
            tileerror: (e) => {
              // A failed tile fetch must never leave a black/blank hole --
              // log it and move on; Leaflet already retries transient failures.
              console.warn("[map] tile failed to load:", e?.tile?.src);
            },
          }}
        />
        {!readOnly && <ClickHandler onMapClick={onMapClick} />}
        <FitBounds positions={positions} fitSignal={fitSignal} />
        <VisibilitySync visible={visible} />
        {markers.map((m) => (
          <Marker
            key={m.id}
            position={[m.latitude, m.longitude]}
            icon={getIcon(m.severity || "NONE", m.id === activeMarkerId, m.priorityRank)}
            eventHandlers={onMarkerClick ? { click: () => onMarkerClick(m.id) } : undefined}
          >
            <Popup>
              <div className="map-pin-popup">
                <div className="map-pin-popup__title">{m.label}</div>
                {m.severity && (
                  <div className="map-pin-popup__severity" style={{ color: severityMeta(m.severity).color }}>
                    {severityMeta(m.severity).label}
                    {m.priorityRank ? ` · Priority #${m.priorityRank}` : ""}
                  </div>
                )}
                {m.numImages != null && <div className="map-pin-popup__row">{m.numImages} image{m.numImages === 1 ? "" : "s"}</div>}
                {m.hazards && m.hazards.length > 0 && (
                  <div className="map-pin-popup__row">Hazards: {m.hazards.join(", ")}</div>
                )}
                {m.recommendedAction && (
                  <div className="map-pin-popup__action">{m.recommendedAction}</div>
                )}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}

// Memoized: re-renders only when props actually change -- prevents the map
// (and every marker) from re-rendering when unrelated App state changes
// elsewhere (e.g. a different tab's content updating).
export default memo(LocationMap);

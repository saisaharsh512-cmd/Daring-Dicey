import MapPanel from "../MapPanel";

/**
 * Thin wrapper -- the actual "never unmount" logic lives in App.jsx, which
 * renders this component unconditionally and only toggles a CSS class on
 * its wrapping element based on the active tab. This component itself has
 * no idea whether it's currently visible except via the `visible` prop,
 * which only controls the Leaflet invalidateSize timing inside LocationMap.
 */
export default function MapPage({ queue, activeImageId, onMapClick, result, visible }) {
  return (
    <div className="page page--map">
      <MapPanel queue={queue} activeImageId={activeImageId} onMapClick={onMapClick} result={result} visible={visible} />
    </div>
  );
}

import { useState, useRef, useCallback, useEffect } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";

// Nominatim: OpenStreetMap's free geocoding service -- no API key, consistent
// with the tile provider already used for the map itself. Browsers disallow
// overriding the User-Agent header from fetch(), so Nominatim's documented
// usage-policy header can't be set client-side; this is fine for light,
// interactive, human-driven search traffic (which is all this is -- one
// request per debounced keystroke pause, aborted/superseded on the next
// keystroke), but heavy/automated use should go through a backend proxy
// with a proper User-Agent instead.
const NOMINATIM_URL = "https://nominatim.openstreetmap.org/search";
const DEBOUNCE_MS = 500;
const MIN_QUERY_LENGTH = 3;
const RESULT_LIMIT = 5;

/**
 * Rendered as a child of <MapContainer> (same pattern as FitBounds/
 * VisibilitySync) so it can pan/zoom the map directly via useMap().
 *
 * Selecting a result:
 *   1. Always flies the map to that location (read-only or assignment mode).
 *   2. If onMapClick is provided (i.e. not read-only / a location is being
 *      assigned), also calls it with {latitude, longitude} -- the EXACT
 *      same callback a real map click would trigger, so search and
 *      click-to-place share one code path and one behavior.
 */
export default function LocationSearch({ onMapClick, disabled = false }) {
  const map = useMap();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [error, setError] = useState(null);
  const debounceRef = useRef(null);
  const abortRef = useRef(null);
  const containerRef = useRef(null);

  const runSearch = useCallback((q) => {
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);

    const url = `${NOMINATIM_URL}?format=jsonv2&q=${encodeURIComponent(q)}&limit=${RESULT_LIMIT}&addressdetails=0`;
    fetch(url, { signal: controller.signal, headers: { Accept: "application/json" } })
      .then((res) => {
        if (!res.ok) throw new Error(`Search failed (${res.status})`);
        return res.json();
      })
      .then((data) => {
        setResults(Array.isArray(data) ? data : []);
        setOpen(true);
        setHighlightedIndex(-1);
      })
      .catch((err) => {
        if (err.name === "AbortError") return; // superseded by a newer keystroke -- not a real error
        setError("Search unavailable right now.");
        setResults([]);
      })
      .finally(() => setLoading(false));
  }, []);

  const handleChange = (e) => {
    const value = e.target.value;
    setQuery(value);
    clearTimeout(debounceRef.current);

    if (value.trim().length < MIN_QUERY_LENGTH) {
      setResults([]);
      setOpen(false);
      setLoading(false);
      return;
    }

    debounceRef.current = setTimeout(() => runSearch(value.trim()), DEBOUNCE_MS);
  };

  const selectResult = useCallback(
    (result) => {
      const latitude = parseFloat(result.lat);
      const longitude = parseFloat(result.lon);
      if (Number.isNaN(latitude) || Number.isNaN(longitude)) return;

      map.flyTo([latitude, longitude], 15, { duration: 0.8 });
      onMapClick?.({ latitude, longitude });

      setQuery(result.display_name);
      setOpen(false);
      setResults([]);
    },
    [map, onMapClick]
  );

  const handleKeyDown = (e) => {
    if (!open || results.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (highlightedIndex >= 0) selectResult(results[highlightedIndex]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const handleClear = () => {
    setQuery("");
    setResults([]);
    setOpen(false);
    setError(null);
  };

  // Close the dropdown on outside click, without interfering with map drag/click.
  useEffect(() => {
    const onDocClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  useEffect(() => () => clearTimeout(debounceRef.current), []);

  // THE actual fix for clicks leaking through to the map: React's synthetic
  // onClick/onMouseDown props are delegated to the app's root DOM node, so
  // they fire AFTER Leaflet's own native listener (attached directly on the
  // map container, which sits between this element and React's root) has
  // already processed the click. Leaflet's own L.DomEvent.disableClickPropagation
  // attaches a real native listener directly on THIS element instead, which
  // fires first in the bubble order and correctly stops the event before it
  // ever reaches the map's click-to-place-marker handler.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    L.DomEvent.disableClickPropagation(el);
    L.DomEvent.disableScrollPropagation(el);
  }, []);

  return (
    <div
      ref={containerRef}
      className="map-search"
    >
      <div className="map-search__box">
        <span className="map-search__icon" aria-hidden="true">
          {loading ? <span className="map-search__spinner" /> : "🔍"}
        </span>
        <input
          type="text"
          className="map-search__input"
          placeholder={disabled ? "Search is unavailable" : "Search for a place…"}
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onFocus={() => results.length > 0 && setOpen(true)}
          disabled={disabled}
          aria-label="Search for a place on the map"
          aria-autocomplete="list"
          aria-expanded={open}
        />
        {query && (
          <button type="button" className="map-search__clear" onClick={handleClear} aria-label="Clear search">
            ✕
          </button>
        )}
      </div>

      {open && (results.length > 0 || error) && (
        <ul className="map-search__results" role="listbox">
          {error && <li className="map-search__error">{error}</li>}
          {results.map((r, i) => (
            <li
              key={r.place_id}
              role="option"
              aria-selected={i === highlightedIndex}
              className={`map-search__result ${i === highlightedIndex ? "map-search__result--highlighted" : ""}`}
              onMouseEnter={() => setHighlightedIndex(i)}
              onClick={() => selectResult(r)}
            >
              <span className="map-search__result-pin">📍</span>
              <span className="map-search__result-text">{r.display_name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

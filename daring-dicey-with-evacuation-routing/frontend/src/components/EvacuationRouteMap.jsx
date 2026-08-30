import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from "react-leaflet";
import { useEffect } from "react";
import L from "leaflet";

const safeIcon = L.divIcon({
  className: "safe-zone-pin-wrapper",
  html: '<span class="safe-zone-pin">✓</span>',
  iconSize: [28, 28],
  iconAnchor: [14, 14],
});

function FitRoute({ points }) {
  const map = useMap();
  useEffect(() => {
    if (points.length > 1) map.fitBounds(points, { padding: [35, 35] });
  }, [map, points]);
  return null;
}

export default function EvacuationRouteMap({ route }) {
  if (!route) return null;
  const origin = [route.origin.latitude, route.origin.longitude];
  const destination = [route.destination.latitude, route.destination.longitude];
  const line = route.geometry.map(([lng, lat]) => [lat, lng]);

  return (
    <div className="evac-route-map">
      <MapContainer center={origin} zoom={13} scrollWheelZoom style={{ height: "100%", width: "100%" }}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />
        <Polyline positions={line} pathOptions={{ weight: 6 }} />
        <Marker position={origin}>
          <Popup>Evacuation origin</Popup>
        </Marker>
        <Marker position={destination} icon={safeIcon}>
          <Popup>{route.destination.name}</Popup>
        </Marker>
        <FitRoute points={[origin, destination]} />
      </MapContainer>
    </div>
  );
}

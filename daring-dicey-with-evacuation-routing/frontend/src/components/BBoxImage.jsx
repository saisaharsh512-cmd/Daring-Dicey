import { useEffect, useRef, useState } from "react";

const MODEL_COLORS = {
  road: "#2fd3c9",
  building: "#e5484d",
  fire: "#f2843c",
  debris: "#e8b93a",
  earthquake: "#b285f0",
  flood: "#4fa3f2",
};

// Only "detection" evidence_type is a real learned object detector's
// bounding box. "whole_image" (flood classifier) and "regional_evidence"
// (earthquake's CLIP grid-tile heuristic) never get boxes drawn, and are
// labeled accordingly -- per the backend's own explicit distinction.
export default function BBoxImage({ previewUrl, filename, detections }) {
  const boxed = detections.filter((d) => d.evidence_type === "detection" && Array.isArray(d.bbox));
  const unboxed = detections.filter((d) => !(d.evidence_type === "detection" && Array.isArray(d.bbox)));

  return (
    <figure className="bbox-figure">
      <div className="bbox-figure__frame">
        <img src={previewUrl} alt={filename} />
        <div className="bbox-figure__boxes">
          {boxed.map((d, i) => (
            <BBoxRect key={i} detection={d} />
          ))}
        </div>
      </div>
      <figcaption>
        <span className="mono">{filename}</span>
        {boxed.length > 0 && <span className="bbox-figure__tag">object detection</span>}
        {unboxed.length > 0 && unboxed.some((d) => d.evidence_type === "regional_evidence") && (
          <span className="bbox-figure__tag bbox-figure__tag--heuristic">heuristic regional evidence — not a bounding-box detector</span>
        )}
        {unboxed.length > 0 && unboxed.some((d) => d.evidence_type === "whole_image") && (
          <span className="bbox-figure__tag bbox-figure__tag--heuristic">whole-image classification — no localization</span>
        )}
      </figcaption>
    </figure>
  );
}

function BBoxRect({ detection }) {
  // bbox is [x1, y1, x2, y2] in source-image pixel space. We render it as a
  // percentage box against a container that's the same aspect ratio as the
  // image (the <img> is width:100%, height:auto inside a relative frame),
  // so we need the image's natural size to convert. We read it lazily via
  // a hidden Image() the first time -- simplest reliable approach without
  // extra state plumbing per-box.
  const color = MODEL_COLORS[detection.model] || "var(--signal)";
  return (
    <NaturalSizedBox bbox={detection.bbox} color={color} label={`${detection.damage_type} ${(detection.confidence * 100).toFixed(0)}%`} />
  );
}

function NaturalSizedBox({ bbox, color, label }) {
  // Finds the nearest <img> sibling in the frame to read naturalWidth/Height.
  const ref = useRef(null);
  const [style, setStyle] = useState(null);

  useEffect(() => {
    const frame = ref.current?.closest(".bbox-figure__frame");
    const img = frame?.querySelector("img");
    if (!img) return;

    const apply = () => {
      if (!img.naturalWidth || !img.naturalHeight) return;
      const [x1, y1, x2, y2] = bbox;
      setStyle({
        left: `${(x1 / img.naturalWidth) * 100}%`,
        top: `${(y1 / img.naturalHeight) * 100}%`,
        width: `${((x2 - x1) / img.naturalWidth) * 100}%`,
        height: `${((y2 - y1) / img.naturalHeight) * 100}%`,
        borderColor: color,
      });
    };

    if (img.complete) apply();
    else img.addEventListener("load", apply, { once: true });
  }, [bbox, color]);

  return (
    <div ref={ref} className="bbox-rect" style={style || { display: "none" }}>
      <span className="bbox-rect__label" style={{ background: color }}>{label}</span>
    </div>
  );
}

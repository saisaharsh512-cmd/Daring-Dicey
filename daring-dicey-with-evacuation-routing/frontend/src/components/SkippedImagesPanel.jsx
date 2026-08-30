export default function SkippedImagesPanel({ skippedImages, imageIdMap }) {
  if (!skippedImages || skippedImages.length === 0) return null;

  const displayName = (path) => {
    if (!path) return "(unknown file)";
    const basename = path.split("/").pop().split("\\").pop();
    return imageIdMap?.[basename] || basename;
  };

  return (
    <section className="panel skipped-panel">
      <div className="panel__title">
        <h2>Skipped Images</h2>
        <p>Rejected by the backend's own validation before any model ran.</p>
      </div>
      <ul className="skipped-list">
        {skippedImages.map((s, i) => (
          <li key={i}>
            <strong>{displayName(s.image_path)}</strong>
            {s.image_error && <span className="skipped-list__reason">{s.image_error}</span>}
            {s.location_error && <span className="skipped-list__reason">{s.location_error}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}

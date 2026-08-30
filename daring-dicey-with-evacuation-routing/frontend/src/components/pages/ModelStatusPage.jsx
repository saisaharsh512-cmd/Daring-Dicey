const STATUS_META = {
  success: { icon: "✓", text: "SUCCESS", tone: "ok" },
  error: { icon: "✕", text: "FAILED", tone: "fail" },
  unavailable: { icon: "⚠", text: "UNAVAILABLE", tone: "warn" },
  gate_blocked: { icon: "—", text: "NOT RUN (gate blocked)", tone: "muted" },
  not_relevant: { icon: "—", text: "NOT RUN (not relevant)", tone: "muted" },
  not_run: { icon: "—", text: "NOT RUN", tone: "muted" },
};

const MODEL_INFO = {
  road: { label: "Road Damage", purpose: "Detects road cracks/potholes via a local YOLOv8 object detector." },
  building: { label: "Building Damage", purpose: "Binary damaged/undamaged building detector (YOLOv10, local)." },
  flood: { label: "Flood", purpose: "Whole-image flood classifier (no localization)." },
  fire: { label: "Fire / Smoke", purpose: "Local YOLOv8 detector for fire and smoke." },
  earthquake: { label: "Earthquake", purpose: "CLIP zero-shot scene relevance + heuristic regional evidence, not a trained detector." },
  debris: { label: "Debris", purpose: "Local YOLOv8-seg model (reuses the building-damage repo's segmentation checkpoint)." },
};

export default function ModelStatusPage({ result }) {
  if (!result) {
    return <div className="page"><div className="panel empty-panel"><p>Run an analysis to see model status here.</p></div></div>;
  }

  return (
    <div className="page">
      <section className="panel">
        <div className="panel__title">
          <h2>Model Status</h2>
          <p>A model error or unavailable dependency is never treated as a detection. Models that never ran are shown as skipped, not as "0 detections".</p>
        </div>
        <div className="model-status-grid">
          {result.model_status.map((m) => {
            const meta = STATUS_META[m.status] || { icon: "?", text: m.status, tone: "muted" };
            const info = MODEL_INFO[m.model] || { label: m.model, purpose: "" };
            return (
              <div key={m.model} className={`model-status-card model-status-card--${meta.tone}`}>
                <div className="model-status-card__header">
                  <span>{info.label}</span>
                  <span className="model-status-card__badge mono">{meta.icon} {meta.text}</span>
                </div>
                <p className="model-status-card__purpose">{info.purpose}</p>
                {m.reason && <p className="model-status-card__reason">{m.reason}</p>}
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}

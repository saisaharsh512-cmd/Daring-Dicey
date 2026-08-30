const STATUS_META = {
  success: { icon: "✓", text: "Successful", tone: "ok" },
  error: { icon: "✕", text: "Failed", tone: "fail" },
  unavailable: { icon: "⚠", text: "Unavailable", tone: "warn" },
  gate_blocked: { icon: "○", text: "Skipped (gate blocked)", tone: "muted" },
  not_relevant: { icon: "○", text: "Skipped (not relevant)", tone: "muted" },
  not_run: { icon: "○", text: "Skipped", tone: "muted" },
};

const MODEL_LABELS = {
  road: "Road Damage",
  building: "Building Damage",
  flood: "Flood",
  fire: "Fire / Smoke",
  earthquake: "Earthquake (CLIP zero-shot)",
  debris: "Debris",
};

/**
 * modelStatus: [{model, status, reason}], straight from the backend's
 * report.model_status. Never re-derives status client-side -- a model
 * failure or gate-block is always what the backend actually reported,
 * never inferred/guessed here.
 */
export default function ModelStatusPanel({ modelStatus }) {
  if (!modelStatus || modelStatus.length === 0) return null;

  return (
    <section className="panel">
      <div className="panel__title">
        <h2>Model Status</h2>
        <p>A model error or unavailable dependency is never treated as a detection.</p>
      </div>
      <ul className="model-status-list">
        {modelStatus.map((m) => {
          const meta = STATUS_META[m.status] || { icon: "?", text: m.status, tone: "muted" };
          return (
            <li key={m.model} className={`model-status-list__item model-status-list__item--${meta.tone}`}>
              <span className="model-status-list__icon">{meta.icon}</span>
              <span className="model-status-list__name">{MODEL_LABELS[m.model] || m.model}</span>
              <span className="model-status-list__text mono">{meta.text}</span>
              {m.reason && <span className="model-status-list__reason">{m.reason}</span>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

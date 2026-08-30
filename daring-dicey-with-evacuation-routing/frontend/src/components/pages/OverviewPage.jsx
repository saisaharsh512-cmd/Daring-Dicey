import { severityMeta } from "../../severity";

const STATUS_META = {
  DISASTER_DETECTED: { text: "DISASTER DETECTED", tone: "ok", icon: "🚨" },
  NOT_A_DISASTER: { text: "NOT A DISASTER", tone: "not-disaster", icon: "✓" },
  UNCERTAIN_NOT_A_DISASTER: { text: "UNCERTAIN", tone: "uncertain", icon: "⚠" },
  NOT_RELEVANT_TO_SELECTED_TYPE: { text: "NOT RELEVANT TO SELECTED TYPE", tone: "not-disaster", icon: "✓" },
  UNCERTAIN_TYPE_RELEVANCE: { text: "UNCERTAIN", tone: "uncertain", icon: "⚠" },
};

export default function OverviewPage({ result, setActiveTab }) {
  if (!result) {
    return (
      <div className="page">
        <div className="panel empty-panel">
          <p>Upload images, place each on the Map tab, and run ANALYZE DISASTER to see the command-center overview here.</p>
        </div>
      </div>
    );
  }

  const { locations, hazards, evacuation_plan, model_status, gate_status, report } = result;
  const disasterLocations = locations.filter((l) => l.is_disaster);
  const criticalLocations = disasterLocations.filter((l) => l.severity_level === "CRITICAL");
  const highLocations = disasterLocations.filter((l) => l.severity_level === "HIGH");
  const statusMeta = STATUS_META[gate_status] || { text: gate_status, tone: "not-disaster", icon: "?" };
  const availableModels = model_status.filter((m) => m.status === "success").length;
  const topPriority = evacuation_plan.priorities[0];

  return (
    <div className="page">
      <section className={`panel overview-hero overview-hero--${statusMeta.tone}`}>
        <span className="overview-hero__icon">{statusMeta.icon}</span>
        <div>
          <div className="overview-hero__status">{statusMeta.text}</div>
          {result.is_disaster && (
            <div className="overview-hero__sub">
              {report.disaster_category_label} · Overall severity: <strong>{result.overall_severity}</strong>
            </div>
          )}
        </div>
      </section>

      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-card__label">Affected Locations</div>
          <div className="kpi-card__value">{disasterLocations.length}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-card__label">Images Analyzed</div>
          <div className="kpi-card__value">{report.num_images_analyzed}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-card__label">Critical Locations</div>
          <div className="kpi-card__value" style={{ color: "var(--sev-critical)" }}>{criticalLocations.length}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-card__label">High-Risk Locations</div>
          <div className="kpi-card__value" style={{ color: "var(--sev-high)" }}>{highLocations.length}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-card__label">Model Availability</div>
          <div className="kpi-card__value">{availableModels}/{model_status.length}</div>
        </div>
      </div>

      {result.is_disaster && hazards.length > 0 && (
        <section className="panel">
          <div className="panel__title"><h2>Detected Hazards</h2></div>
          <ul className="tag-list">
            {hazards.map((h) => <li key={h} className="tag">{h}</li>)}
          </ul>
        </section>
      )}

      {result.is_disaster && topPriority && (
        <section className="panel overview-action">
          <div className="panel__title"><h2>Immediate Action</h2></div>
          <p className="overview-action__text">
            Evacuate <button className="link-btn" onClick={() => setActiveTab("map")}>{topPriority.location_id.replace("_", " ")}</button> first
            (<span style={{ color: severityMeta(topPriority.severity_level).color }}>{topPriority.severity_level}</span>, priority #{topPriority.priority_rank}).
          </p>
          <p className="overview-action__reason">{topPriority.reason}</p>
          <button className="link-btn" onClick={() => setActiveTab("recommendations")}>View full recommendations →</button>
        </section>
      )}

      {!result.is_disaster && (
        <section className="panel">
          <p className="empty-note">
            No sufficient disaster-related visual evidence was detected. Specialized hazard models were not
            executed for this batch — see the Model Status tab for details.
          </p>
        </section>
      )}
    </div>
  );
}

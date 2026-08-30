import { severityMeta } from "../../severity";

function RecommendationItem({ rec }) {
  const meta = severityMeta(rec.priority);
  return (
    <li className="rec-item">
      <span className="rec-item__badge mono" style={{ color: meta.color, borderColor: meta.color }}>{rec.priority}</span>
      <div className="rec-item__body">
        <div className="rec-item__action">{rec.action}</div>
        <div className="rec-item__meta mono">
          {rec.hazard} · {rec.location.replace("_", " ")}
          {rec.confidence != null && ` · ${(rec.confidence * 100).toFixed(0)}% confidence`}
        </div>
        <div className="rec-item__reason">{rec.reason}</div>
      </div>
    </li>
  );
}

function RecSection({ icon, title, items, emptyText }) {
  return (
    <section className="panel rec-section">
      <div className="panel__title"><h2>{icon} {title}</h2></div>
      {items.length > 0 ? (
        <ul className="rec-list">
          {items.map((r, i) => <RecommendationItem key={i} rec={r} />)}
        </ul>
      ) : (
        <p className="empty-note">{emptyText}</p>
      )}
    </section>
  );
}

export default function RecommendationsPage({ result }) {
  if (!result) {
    return <div className="page"><div className="panel empty-panel"><p>Run an analysis to see recommendations here.</p></div></div>;
  }

  if (!result.is_disaster) {
    return (
      <div className="page">
        <div className="panel">
          <p className="empty-note">No recommendations to show — no disaster-confirmed evidence in this batch.</p>
        </div>
      </div>
    );
  }

  const { recommendations, evacuation_plan } = result;

  return (
    <div className="page">
      <p className="disclaimer-note disclaimer-note--top">{recommendations.disclaimer}</p>

      <RecSection icon="🚨" title="Immediate Actions" items={recommendations.immediate_actions}
                  emptyText="No immediate-action recommendations were generated." />

      <section className="panel rec-section">
        <div className="panel__title"><h2>🚑 Evacuation Priorities</h2></div>
        {evacuation_plan.priorities.length > 0 ? (
          <ol className="rec-evac-list">
            {evacuation_plan.priorities.map((p) => {
              const meta = severityMeta(p.severity_level);
              return (
                <li key={p.location_id}>
                  <span className="mono" style={{ color: meta.color }}>#{p.priority_rank} {p.location_id.replace("_", " ")} — {meta.label}</span>
                  <p>{p.reason}</p>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="empty-note">No evacuation priorities computed.</p>
        )}
      </section>

      <RecSection icon="🧯" title="Hazard-Specific Actions" items={recommendations.hazard_specific_actions}
                  emptyText="No hazard-specific actions were generated." />

      <RecSection icon="⛔" title="Do Not Do" items={recommendations.avoid}
                  emptyText="No avoidance warnings were generated." />

      <RecSection icon="📦" title="Resource Priorities" items={recommendations.resource_priorities}
                  emptyText="No resource-priority recommendations were generated." />
    </div>
  );
}

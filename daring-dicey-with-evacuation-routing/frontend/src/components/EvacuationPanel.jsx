import { severityMeta } from "../severity";

export default function EvacuationPanel({ evacuationPlan }) {
  if (!evacuationPlan || evacuationPlan.priorities.length === 0) return null;

  return (
    <section className="panel evac-panel">
      <div className="panel__title">
        <h2>Evacuation Priority</h2>
        <p>{evacuationPlan.disclaimer}</p>
      </div>
      <ol className="evac-list">
        {evacuationPlan.priorities.map((p) => {
          const meta = severityMeta(p.severity_level);
          return (
            <li key={p.location_id} className="evac-list__item">
              <a href={`#${p.location_id}`} className="evac-list__rank mono" style={{ color: meta.color }}>
                #{p.priority_rank}
              </a>
              <div className="evac-list__body">
                <div className="evac-list__title">
                  <span>{p.location_id.replace("_", " ")}</span>
                  <span className="mono" style={{ color: meta.color }}>{meta.label}</span>
                </div>
                <p className="evac-list__reason">{p.reason}</p>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

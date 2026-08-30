import { fmtCoord } from "../severity";

export default function InfrastructurePanel({ locations }) {
  const rows = [];
  for (const loc of locations) {
    for (const c of loc.infrastructure_constraints) {
      rows.push({ ...c, location_id: loc.location_id });
    }
  }

  return (
    <section className="panel infra-panel">
      <div className="panel__title">
        <h2>Infrastructure Constraints</h2>
        <p>For the mapping/evacuation team — routes should avoid or account for these.</p>
      </div>
      {rows.length === 0 ? (
        <p className="empty-note">No hard infrastructure constraints were flagged in this analysis.</p>
      ) : (
        <table className="infra-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Status</th>
              <th>Evidence</th>
              <th>Confidence</th>
              <th>Location</th>
              <th>Coordinates</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="mono">{r.type}</td>
                <td>
                  <span className={`constraint-badge constraint-badge--${r.status}`}>{r.status}</span>
                </td>
                <td>{r.damage_type}</td>
                <td className="mono">{(r.confidence * 100).toFixed(0)}%</td>
                <td>{r.location_id.replace("_", " ")}</td>
                <td className="mono">{fmtCoord(r.location.latitude)}, {fmtCoord(r.location.longitude)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

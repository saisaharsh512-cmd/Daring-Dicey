import { severityMeta, fmtScore } from "../severity";

export default function PriorityLadder({ locations }) {
  return (
    <div className="ladder">
      {locations.map((loc) => {
        const meta = severityMeta(loc.severity_level);
        return (
          <a href={`#${loc.location_id}`} key={loc.location_id} className="ladder__rung" style={{ "--rung-color": meta.color }}>
            <span className="ladder__rank mono">#{loc.priority_rank}</span>
            <span className="ladder__meter">
              <span className="ladder__meter-fill" style={{ width: `${loc.severity_score}%` }} />
            </span>
            <span className="ladder__info">
              <span className="ladder__location">{loc.location_id.replace("_", " ")}</span>
              <span className="ladder__level mono">{meta.label}</span>
            </span>
            <span className="ladder__score mono">{fmtScore(loc.severity_score)}</span>
          </a>
        );
      })}
    </div>
  );
}

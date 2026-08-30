import { severityMeta, fmtScore, fmtCoord } from "../severity";
import EvidenceGallery from "./EvidenceGallery";

const GATE_STATUS_TEXT = {
  NOT_A_DISASTER: "Not a disaster",
  UNCERTAIN_NOT_A_DISASTER: "Uncertain",
  NOT_RELEVANT_TO_SELECTED_TYPE: "Not relevant to selected disaster type",
  UNCERTAIN_TYPE_RELEVANCE: "Uncertain type relevance",
};

export default function LocationCard({ location, submittedImages }) {
  const meta = severityMeta(location.severity_level);
  const damageTypes = Array.from(new Set(location.detected_damage.map((d) => d.damage_type)));
  const modelErrorEntries = Object.entries(location.model_errors || {});

  return (
    <article id={location.location_id} className={`loc-card ${!location.is_disaster ? "loc-card--not-disaster" : ""}`} style={{ "--rung-color": meta.color }}>
      <div className="loc-card__rail" />
      <div className="loc-card__body">
        <header className="loc-card__header">
          <div className="loc-card__rank mono">{location.is_disaster ? `#${location.priority_rank}` : "—"}</div>
          <div>
            <h3>{location.location_id.replace("_", " ")}</h3>
            <p className="mono loc-card__coords">
              {fmtCoord(location.latitude)}, {fmtCoord(location.longitude)} · {location.num_images} image{location.num_images === 1 ? "" : "s"}
            </p>
          </div>
          <div className="loc-card__severity">
            <span className="loc-card__level mono" style={{ color: meta.color }}>
              {location.is_disaster ? meta.label : (GATE_STATUS_TEXT[location.gate_status] || "Not a disaster")}
            </span>
            {location.is_disaster && (
              <span className="loc-card__score mono">{fmtScore(location.severity_score)}<span className="loc-card__score-suffix">/100</span></span>
            )}
          </div>
        </header>

        <p className="loc-card__explanation">{location.severity_explanation}</p>

        {location.is_disaster && (
          <>
            <section className="loc-card__section">
              <h4>Damage Detected</h4>
              {damageTypes.length > 0 ? (
                <ul className="tag-list">
                  {damageTypes.map((t) => (
                    <li key={t} className="tag">{t}</li>
                  ))}
                </ul>
              ) : (
                <p className="empty-note">No damage evidence detected at this location.</p>
              )}
            </section>

            {location.infrastructure_constraints.length > 0 && (
              <section className="loc-card__section">
                <h4>Infrastructure Constraints</h4>
                <ul className="constraint-list">
                  {location.infrastructure_constraints.map((c, i) => (
                    <li key={i} className="constraint-list__item">
                      <span className={`constraint-badge constraint-badge--${c.status}`}>{c.type} · {c.status}</span>
                      <span>{c.damage_type}</span>
                      <span className="mono constraint-list__confidence">{(c.confidence * 100).toFixed(0)}%</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}

        {modelErrorEntries.length > 0 && (
          <section className="loc-card__section loc-card__section--warn">
            <h4>Model Errors</h4>
            <ul className="error-list">
              {modelErrorEntries.map(([model, errs]) =>
                errs.map((e, i) => (
                  <li key={`${model}-${i}`}>
                    <strong>{model}</strong> — {e.error}
                  </li>
                ))
              )}
            </ul>
            <p className="field-hint">
              This model's evidence is simply absent from the score above — never fabricated.
            </p>
          </section>
        )}

        {location.is_disaster && (
          <section className="loc-card__section">
            <h4>Model Evidence</h4>
            <EvidenceGallery detectedDamage={location.detected_damage} submittedImages={submittedImages} />
          </section>
        )}
      </div>
    </article>
  );
}

const GATE_META = {
  DISASTER_DETECTED: {
    text: "DISASTER DETECTED", tone: "ok",
    explain: (report) => `Classified as ${report.disaster_category_label}. Specialized models were run only after both relevance gates passed.`,
  },
  NOT_A_DISASTER: {
    text: "NOT A DISASTER", tone: "not-disaster",
    explain: () => "No meaningful disaster evidence detected. Specialized disaster models were not run.",
  },
  UNCERTAIN_NOT_A_DISASTER: {
    text: "UNCERTAIN", tone: "uncertain",
    explain: () => "The system could not confidently determine whether this image contains disaster evidence. Specialized models were not run.",
  },
  NOT_RELEVANT_TO_SELECTED_TYPE: {
    text: "NOT RELEVANT TO SELECTED DISASTER TYPE", tone: "not-disaster",
    explain: (report) => `The image may show something disaster-related, but not "${report.selected_disaster}" specifically. Specialized models were not run.`,
  },
  UNCERTAIN_TYPE_RELEVANCE: {
    text: "UNCERTAIN", tone: "uncertain",
    explain: () => "The system could not confidently determine relevance to the selected disaster type. Specialized models were not run.",
  },
};

function pct(v) {
  return typeof v === "number" ? `${(v * 100).toFixed(0)}%` : "—";
}

export default function GateStatusPanel({ report, gateStatus }) {
  const meta = GATE_META[gateStatus] || { text: gateStatus, tone: "not-disaster", explain: () => "" };

  return (
    <section className={`panel gate-panel gate-panel--${meta.tone}`}>
      <div className="gate-panel__status">{meta.text}</div>
      <p className="gate-panel__explain">{meta.explain(report)}</p>

      <div className="gate-panel__grid mono">
        <div>
          <span>Disaster relevance</span>
          <strong>{pct(report.disaster_confidence)}</strong>
        </div>
        {report.type_relevance !== null && report.type_relevance !== undefined && (
          <div>
            <span>{report.selected_disaster} relevance</span>
            <strong>{pct(report.type_relevance)}</strong>
          </div>
        )}
        <div>
          <span>Severity</span>
          <strong>{report.overall_severity_level}</strong>
        </div>
      </div>
    </section>
  );
}

import { useCallback } from "react";

function downloadTextFile(filename, text) {
  const blob = new Blob([text], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function IncidentReportPage({ result }) {
  const handleExport = useCallback(() => {
    if (!result) return;
    const { llm_report, disaster_type, report } = result;
    const header = `DISASTER RESPONSE INCIDENT REPORT\nGenerated from AI-assisted image analysis\nDisaster type: ${disaster_type}\nStatus: ${report.overall_status}\nSeverity: ${report.overall_severity_level}\n\n`;
    downloadTextFile(`incident-report-${Date.now()}.txt`, header + llm_report.text);
  }, [result]);

  if (!result) {
    return <div className="page"><div className="panel empty-panel"><p>Run an analysis to generate an incident report here.</p></div></div>;
  }

  const { llm_report, report, locations, evacuation_plan, model_status, hazards } = result;
  const disasterLocations = locations.filter((l) => l.is_disaster);

  return (
    <div className="page">
      <section className="panel report-header">
        <div>
          <h2>Incident Report</h2>
          <p className="field-hint">Generated from AI-assisted image analysis. Distinguish AI-generated recommendations from verified emergency information before acting.</p>
        </div>
        <button className="analyze-btn analyze-btn--compact" onClick={handleExport}>Export Report (.txt)</button>
      </section>

      <section className="panel">
        <div className="report-summary-grid">
          <div><span>Disaster Type</span><strong>{report.disaster_category_label}</strong></div>
          <div><span>Overall Severity</span><strong>{report.overall_severity_level}</strong></div>
          <div><span>Affected Locations</span><strong>{disasterLocations.length}</strong></div>
          <div><span>Detected Hazards</span><strong>{hazards.length}</strong></div>
          <div><span>Evacuation Priorities</span><strong>{evacuation_plan.priorities.length}</strong></div>
          <div><span>Models Available</span><strong>{model_status.filter((m) => m.status === "success").length}/{model_status.length}</strong></div>
        </div>
      </section>

      <section className="panel">
        <div className="panel__title">
          <h2>{llm_report.source === "llm" ? "LLM-Generated Summary" : "Structured Summary (LLM unavailable)"}</h2>
          {llm_report.source === "fallback" && (
            <p className="report-panel__source report-panel__source--fallback">{llm_report.error}</p>
          )}
        </div>
        {llm_report.sections ? (
          <div className="report-panel__sections">
            {Object.entries(llm_report.sections).map(([heading, body]) => (
              <div key={heading} className="report-panel__section">
                <h4>{heading}</h4>
                <p>{body}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="report-panel__text">{llm_report.text}</div>
        )}
      </section>
    </div>
  );
}

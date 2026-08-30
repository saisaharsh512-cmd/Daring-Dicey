import { useEffect, useState } from "react";

// This is a client-side ESTIMATED progression through the known pipeline
// stages, not a live-synced readout of the backend's actual state (the
// backend is a single synchronous HTTP call, no streaming). It's presented
// as a rough illustration of what's happening, not a precise tracker.
const STAGES = [
  "Validating images…",
  "Checking whether images contain disaster evidence…",
  "Checking relevance to selected disaster type…",
  "Running specialized damage models…",
  "Aggregating locations…",
  "Calculating severity & evacuation priority…",
  "Generating incident report…",
];

const STAGE_INTERVAL_MS = 1400;

export default function AnalysisProgress({ imageCount }) {
  const [stageIndex, setStageIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setStageIndex((i) => Math.min(i + 1, STAGES.length - 1));
    }, STAGE_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="panel loading-panel">
      <span className="spinner spinner--lg" />
      <p>Running routed models on {imageCount} image{imageCount === 1 ? "" : "s"}…</p>
      <ul className="progress-stages">
        {STAGES.map((stage, i) => (
          <li key={stage} className={i < stageIndex ? "done" : i === stageIndex ? "active" : "pending"}>
            <span className="progress-stages__icon">{i < stageIndex ? "✓" : i === stageIndex ? "…" : "○"}</span>
            {stage}
          </li>
        ))}
      </ul>
      <p className="field-hint">First run can be slow while models load. This can take a while — please don't close the tab.</p>
    </div>
  );
}

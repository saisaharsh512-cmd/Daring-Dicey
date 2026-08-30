// severity.js
//
// Presentation only. The severity_level string and severity_score number
// used here always come directly from the backend's response
// (scoring/severity_engine.py). This file never computes a score -- it
// only decides what color/label to render for a level the backend already
// assigned.

export const SEVERITY_META = {
  CRITICAL: { color: "var(--sev-critical)", order: 0, label: "CRITICAL" },
  HIGH: { color: "var(--sev-high)", order: 1, label: "HIGH" },
  MODERATE: { color: "var(--sev-moderate)", order: 2, label: "MODERATE" },
  LOW: { color: "var(--sev-low)", order: 3, label: "LOW" },
  NONE: { color: "var(--sev-none)", order: 4, label: "NONE" },
  UNCERTAIN: { color: "var(--sev-uncertain)", order: 5, label: "UNCERTAIN" },
  NOT_DISASTER: { color: "var(--sev-none)", order: 6, label: "NOT A DISASTER" },
};

export function severityMeta(level) {
  return SEVERITY_META[level] || { color: "var(--text-muted)", order: 9, label: level || "UNKNOWN" };
}

export function fmtScore(score) {
  if (typeof score !== "number") return "—";
  return score.toFixed(1);
}

export function fmtCoord(v) {
  if (typeof v !== "number") return "—";
  return v.toFixed(5);
}

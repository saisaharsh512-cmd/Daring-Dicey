import { ShieldAlert } from "lucide-react";
import { API_BASE_URL } from "../api";

export default function TopBar({ backendStatus }) {
  const statusMeta = {
    checking: { label: "CONNECTING", dot: "var(--text-muted)" },
    online: { label: "SYSTEMS ONLINE", dot: "var(--signal)" },
    offline: { label: "BACKEND UNREACHABLE", dot: "var(--sev-critical)" },
  }[backendStatus];

  return (
    <header className="topbar">
      <div className="topbar__brand">
        <span className="topbar__mark"><ShieldAlert size={19} strokeWidth={2.5} /></span>
        <div>
          <h1>DARING DICEY</h1>
          <p>AI-Powered Disaster-Resilient Infrastructure Assessment</p>
        </div>
      </div>
      <div className="topbar__status" title={API_BASE_URL}>
        <span className="topbar__dot" style={{ background: statusMeta.dot, boxShadow: `0 0 8px ${statusMeta.dot}` }} />
        <span className="mono">{statusMeta.label}</span>
      </div>
    </header>
  );
}

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "hazards", label: "Hazard Analysis" },
  { id: "map", label: "Map" },
  { id: "evacuation", label: "Evacuation" },
  { id: "rescue", label: "Rescue Teams" },
  { id: "recommendations", label: "Recommendations" },
  { id: "report", label: "Incident Report" },
  { id: "models", label: "Model Status" },
];

export default function TabNav({ activeTab, setActiveTab, hasResult }) {
  return (
    <nav className="tab-nav">
      {TABS.map((t) => (
        <button
          key={t.id}
          type="button"
          className={`tab-nav__item ${activeTab === t.id ? "tab-nav__item--active" : ""}`}
          onClick={() => setActiveTab(t.id)}
          disabled={t.id !== "overview" && t.id !== "map" && !hasResult}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}

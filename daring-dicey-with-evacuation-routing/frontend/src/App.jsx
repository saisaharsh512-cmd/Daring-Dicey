import { useEffect, useState, useCallback } from "react";
import TopBar from "./components/TopBar";
import TabNav from "./components/TabNav";
import ControlPanel from "./components/ControlPanel";
import AnalysisProgress from "./components/AnalysisProgress";
import ErrorBanner from "./components/ErrorBanner";
import OverviewPage from "./components/pages/OverviewPage";
import HazardAnalysisPage from "./components/pages/HazardAnalysisPage";
import MapPage from "./components/pages/MapPage";
import EvacuationPage from "./components/pages/EvacuationPage";
import RecommendationsPage from "./components/pages/RecommendationsPage";
import IncidentReportPage from "./components/pages/IncidentReportPage";
import ModelStatusPage from "./components/pages/ModelStatusPage";
import RescueTeamsPage from "./components/pages/RescueTeamsPage";
import { analyzeDisaster, checkHealth, fetchDisasterTypes, ApiError } from "./api";
import "./styles/index.css";
import "./styles/app.css";

let nextId = 1;

export default function App() {
  const [backendStatus, setBackendStatus] = useState("checking");
  const [disasterTypes, setDisasterTypes] = useState([{ value: "earthquake", models_run: [] }]);
  const [disasterType, setDisasterType] = useState("earthquake");
  const [queue, setQueue] = useState([]);
  const [activeImageId, setActiveImageId] = useState(null);
  const [toleranceMeters, setToleranceMeters] = useState(75);
  const [totalRescueMembers, setTotalRescueMembers] = useState(0);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState(null);
  const [submittedImages, setSubmittedImages] = useState([]);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const ok = await checkHealth();
      if (!cancelled) setBackendStatus(ok ? "online" : "offline");
      const types = await fetchDisasterTypes();
      if (!cancelled && types.length > 0) {
        setDisasterTypes(types);
        setDisasterType((current) => (types.some((t) => t.value === current) ? current : types[0].value));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const onAddFiles = useCallback((files) => {
    const items = files.map((file) => ({
      id: nextId++,
      file,
      previewUrl: URL.createObjectURL(file),
      latitude: "",
      longitude: "",
    }));
    setQueue((q) => [...q, ...items]);
    setActiveImageId((current) => current ?? items[0]?.id ?? null); // auto-select the first newly-added image if nothing's active yet
    setResult(null); // new images invalidate the previous analysis's map/results
  }, []);

  const onUpdateItem = useCallback((id, patch) => {
    setQueue((q) => q.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }, []);

  const onRemoveItem = useCallback((id) => {
    setQueue((q) => {
      const target = q.find((i) => i.id === id);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return q.filter((i) => i.id !== id);
    });
    setActiveImageId((current) => (current === id ? null : current));
  }, []);

  // Owns the actual coordinate assignment -- MapPage/MapPanel/LocationMap
  // only report a click happened, they don't know about `queue`.
  const handleMapClick = useCallback(
    ({ latitude, longitude }) => {
      if (!activeImageId) return;
      onUpdateItem(activeImageId, { latitude: String(latitude.toFixed(6)), longitude: String(longitude.toFixed(6)) });
      setQueue((currentQueue) => {
        const idx = currentQueue.findIndex((q) => q.id === activeImageId);
        const next = currentQueue.slice(idx + 1).find((q) => q.latitude === "" || q.longitude === "");
        setActiveImageId(next ? next.id : null);
        return currentQueue;
      });
    },
    [activeImageId, onUpdateItem]
  );

  const onAnalyze = useCallback(async () => {
    setError(null);
    setAnalyzing(true);
    setResult(null);
    const snapshot = queue; // freeze the order used for this request, for reliable index-based image matching
    setSubmittedImages(snapshot);
    try {
      const data = await analyzeDisaster(disasterType, snapshot, toleranceMeters, totalRescueMembers);
      setResult(data);
      setBackendStatus("online");
      setActiveTab("overview");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        if (err.status === 0) setBackendStatus("offline");
      } else {
        setError(`Unexpected error: ${err.message}`);
      }
    } finally {
      setAnalyzing(false);
    }
  }, [queue, disasterType, toleranceMeters, totalRescueMembers]);

  return (
    <div className="app">
      <TopBar backendStatus={backendStatus} />
      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      <TabNav activeTab={activeTab} setActiveTab={setActiveTab} hasResult={!!result} />

      <main className="app__shell">
        <ControlPanel
          disasterTypes={disasterTypes}
          disasterType={disasterType}
          setDisasterType={setDisasterType}
          queue={queue}
          onAddFiles={onAddFiles}
          onRemoveItem={onRemoveItem}
          onAnalyze={onAnalyze}
          analyzing={analyzing}
          toleranceMeters={toleranceMeters}
          setToleranceMeters={setToleranceMeters}
          totalRescueMembers={totalRescueMembers}
          setTotalRescueMembers={setTotalRescueMembers}
          activeImageId={activeImageId}
          setActiveImageId={setActiveImageId}
        />

        <div className="app__content">
          {analyzing && <AnalysisProgress imageCount={queue.length} />}

          {/*
            THE MAP KEEP-ALIVE FIX: this wrapper is ALWAYS in the DOM tree --
            never conditionally rendered by activeTab (that would unmount and
            recreate the entire Leaflet instance on every tab switch, which
            was the root cause of the black-map bug). Only a CSS class toggles,
            and `visible` tells LocationMap when to run its invalidateSize fix.
          */}
          <div className={activeTab === "map" && !analyzing ? "tab-page tab-page--visible" : "tab-page"}>
            <MapPage
              queue={queue}
              activeImageId={activeImageId}
              onMapClick={handleMapClick}
              result={result}
              visible={activeTab === "map" && !analyzing}
            />
          </div>

          {!analyzing && activeTab === "overview" && <OverviewPage result={result} setActiveTab={setActiveTab} />}
          {!analyzing && activeTab === "hazards" && <HazardAnalysisPage result={result} submittedImages={submittedImages} />}
          {!analyzing && activeTab === "evacuation" && <EvacuationPage result={result} />}
          {!analyzing && activeTab === "recommendations" && <RecommendationsPage result={result} />}
          {!analyzing && activeTab === "report" && <IncidentReportPage result={result} />}
          {!analyzing && activeTab === "models" && <ModelStatusPage result={result} />}
          {!analyzing && activeTab === "rescue" && <RescueTeamsPage result={result} />}
        </div>
      </main>
    </div>
  );
}

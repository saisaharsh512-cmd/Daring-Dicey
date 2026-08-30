import { useRef } from "react";
import ImageQueueItem from "./ImageQueueItem";

const DISASTER_LABELS = {
  earthquake: "Earthquake",
  flood: "Flood",
  wildfire: "Fire / Wildfire",
  fire: "Fire / Wildfire",
  cyclone: "Cyclone / Storm",
  landslide: "Landslide",
  other: "Other / Unclassified Disaster",
};

export default function ControlPanel({
  disasterTypes,
  disasterType,
  setDisasterType,
  queue,
  onAddFiles,
  onRemoveItem,
  onAnalyze,
  analyzing,
  toleranceMeters,
  setToleranceMeters,
  totalRescueMembers,
  setTotalRescueMembers,
  activeImageId,
  setActiveImageId,
}) {
  const fileInputRef = useRef(null);

  const handleFiles = (fileList) => {
    const files = Array.from(fileList || []).filter((f) => f.type.startsWith("image/"));
    if (files.length > 0) onAddFiles(files);
  };

  const readyCount = queue.filter((q) => q.latitude !== "" && q.longitude !== "").length;
  const canAnalyze = queue.length > 0 && readyCount === queue.length && !analyzing;

  return (
    <section className="panel control-panel">
      <div className="panel__section">
        <label className="field-label" htmlFor="disaster-type">Disaster Type</label>
        <select
          id="disaster-type"
          value={disasterType}
          onChange={(e) => setDisasterType(e.target.value)}
          disabled={analyzing}
        >
          {disasterTypes.map((t) => (
            <option key={t.value} value={t.value}>
              {DISASTER_LABELS[t.value] || t.value}
            </option>
          ))}
        </select>
        {disasterTypes.find((t) => t.value === disasterType)?.models_run?.length > 0 && (
          <p className="field-hint mono">
            models routed: {disasterTypes.find((t) => t.value === disasterType).models_run.join(", ")}
          </p>
        )}
        {disasterType === "other" && (
          <p className="field-hint">
            "Other" is never auto-relabeled to a specific disaster. If disaster-related, it's reported as
            "Other / Unclassified Disaster" with whatever supporting evidence actually applies.
          </p>
        )}
      </div>

      <div className="panel__section">
        <div className="field-label">Upload Images</div>
        <div
          className="dropzone"
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            handleFiles(e.dataTransfer.files);
          }}
        >
          <span className="dropzone__icon">＋</span>
          <span>Drop images or click to browse</span>
          <span className="dropzone__hint mono">JPG · PNG · WEBP — multiple allowed</span>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          hidden
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {queue.length > 0 && (
        <div className="panel__section">
          <div className="field-label">
            Uploaded Images <span className="mono field-label__count">{queue.length}</span>
          </div>
          <ul className="queue-list">
            {queue.map((item, i) => (
              <ImageQueueItem
                key={item.id}
                item={item}
                index={i}
                isActive={item.id === activeImageId}
                onSelect={setActiveImageId}
                onRemove={onRemoveItem}
                disabled={analyzing}
              />
            ))}
          </ul>
        </div>
      )}

      <div className="panel__section">
        <label className="field-label" htmlFor="rescue-members">Available Rescue Members</label>
        <input
          id="rescue-members"
          className="rescue-members-input"
          type="number"
          min="0"
          max="100000"
          step="1"
          value={totalRescueMembers}
          disabled={analyzing}
          onChange={(e) => setTotalRescueMembers(Math.max(0, Number(e.target.value) || 0))}
          placeholder="e.g. 1000"
        />
        <p className="field-hint">
          Total available pool. The AI creates bounded teams and keeps unused members in reserve.
        </p>
      </div>

      <div className="panel__section panel__section--advanced">
        <label className="field-label" htmlFor="tolerance">
          Location cluster tolerance <span className="mono">{toleranceMeters}m</span>
        </label>
        <input
          id="tolerance"
          type="range"
          min="10"
          max="300"
          step="5"
          value={toleranceMeters}
          disabled={analyzing}
          onChange={(e) => setToleranceMeters(Number(e.target.value))}
        />
        <p className="field-hint">Images within this radius are grouped as one location by the backend.</p>
      </div>

      <button className="analyze-btn" onClick={onAnalyze} disabled={!canAnalyze}>
        {analyzing ? (
          <>
            <span className="spinner" /> ANALYZING…
          </>
        ) : (
          "ANALYZE DISASTER"
        )}
      </button>
      {queue.length > 0 && readyCount !== queue.length && (
        <p className="analyze-btn__hint">Set a location on the map for every image to enable analysis.</p>
      )}
    </section>
  );
}

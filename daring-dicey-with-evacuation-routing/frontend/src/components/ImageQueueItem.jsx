export default function ImageQueueItem({ item, index, onSelect, onRemove, isActive, disabled }) {
  const hasLocation = item.latitude !== "" && item.longitude !== "";

  return (
    <li className={`queue-row ${isActive ? "queue-row--active" : ""}`}>
      <img className="queue-row__thumb" src={item.previewUrl} alt="" />
      <div className="queue-row__body">
        <div className="queue-row__name" title={item.file.name}>
          <span className="queue-row__index mono">{String(index + 1).padStart(2, "0")}</span>
          {item.file.name}
        </div>
        {hasLocation ? (
          <div className="queue-row__coords mono">
            📍 {Number(item.latitude).toFixed(4)}, {Number(item.longitude).toFixed(4)}
          </div>
        ) : (
          <div className="queue-row__warn">No location set</div>
        )}
        <button
          type="button"
          className={`queue-row__assign ${isActive ? "queue-row__assign--active" : ""}`}
          onClick={() => onSelect(item.id)}
          disabled={disabled}
        >
          {isActive ? "Click map to set location…" : hasLocation ? "Change location" : "Set location on map"}
        </button>
      </div>
      <button
        type="button"
        className="queue-row__remove"
        onClick={() => onRemove(item.id)}
        disabled={disabled}
        aria-label={`Remove ${item.file.name}`}
      >
        ✕
      </button>
    </li>
  );
}

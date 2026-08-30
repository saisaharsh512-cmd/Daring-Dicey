export default function ErrorBanner({ message, onDismiss }) {
  if (!message) return null;
  return (
    <div className="error-banner" role="alert">
      <span className="error-banner__icon">⚠</span>
      <span className="error-banner__text">{message}</span>
      {onDismiss && (
        <button className="error-banner__dismiss" onClick={onDismiss} aria-label="Dismiss">✕</button>
      )}
    </div>
  );
}

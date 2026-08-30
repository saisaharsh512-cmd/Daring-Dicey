import LocationCard from "../LocationCard";

export default function HazardAnalysisPage({ result, submittedImages }) {
  if (!result) {
    return <div className="page"><div className="panel empty-panel"><p>Run an analysis to see detailed hazard findings here.</p></div></div>;
  }

  const { locations } = result;

  if (locations.length === 0) {
    return (
      <div className="page">
        <div className="panel">
          <p className="empty-note">No locations were produced from this batch — every image was either invalid or missing a valid location.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <section className="panel">
        <div className="panel__title">
          <h2>Hazard Analysis</h2>
          <p>Detailed AI findings per location — model, detection, confidence, and severity contribution.</p>
        </div>
        <div className="loc-card-list">
          {locations.map((loc) => (
            <LocationCard key={loc.location_id} location={loc} submittedImages={submittedImages} />
          ))}
        </div>
      </section>
    </div>
  );
}

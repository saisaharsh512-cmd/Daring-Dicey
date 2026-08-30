import GateStatusPanel from "./GateStatusPanel";
import ModelStatusPanel from "./ModelStatusPanel";
import EvacuationPanel from "./EvacuationPanel";
import IncidentReportPanel from "./IncidentReportPanel";
import LocationCard from "./LocationCard";
import InfrastructurePanel from "./InfrastructurePanel";
import SkippedImagesPanel from "./SkippedImagesPanel";

export default function ResultsView({ result, submittedImages }) {
  const {
    locations, disaster_type, cluster_tolerance_meters, skipped_images, image_id_map,
    is_disaster, gate_status, report, model_status, evacuation_plan, llm_report,
  } = result;

  const disasterLocations = locations.filter((loc) => loc.is_disaster);

  return (
    <div className="results">
      <div className="results__meta mono">
        disaster_type={disaster_type} · cluster_tolerance={cluster_tolerance_meters}m · {locations.length} location{locations.length === 1 ? "" : "s"}
      </div>

      <GateStatusPanel report={report} gateStatus={gate_status} />

      {locations.length === 0 && (
        <section className="panel">
          <p className="empty-note">
            No locations were produced from this batch. Every image was either invalid or missing a valid
            location — see Skipped Images below. This is different from "not a disaster" — it means no
            usable image/location pairs were submitted at all.
          </p>
        </section>
      )}

      {is_disaster && disasterLocations.length > 0 && (
        <EvacuationPanel evacuationPlan={evacuation_plan} />
      )}

      {locations.length > 0 && (
        <section className="panel">
          <div className="panel__title">
            <h2>Location Summary &amp; Damage Evidence</h2>
          </div>
          <div className="loc-card-list">
            {locations.map((loc) => (
              <LocationCard key={loc.location_id} location={loc} submittedImages={submittedImages} />
            ))}
          </div>
        </section>
      )}

      <ModelStatusPanel modelStatus={model_status} />

      {is_disaster && <InfrastructurePanel locations={disasterLocations} />}

      <IncidentReportPanel llmReport={llm_report} />

      <SkippedImagesPanel skippedImages={skipped_images} imageIdMap={image_id_map} />
    </div>
  );
}

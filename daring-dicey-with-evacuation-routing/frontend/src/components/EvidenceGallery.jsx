import BBoxImage from "./BBoxImage";
import { resolveSubmittedImage } from "../imageMatch";

export default function EvidenceGallery({ detectedDamage, submittedImages }) {
  const bySourceImage = new Map();
  for (const d of detectedDamage) {
    if (!bySourceImage.has(d.source_image)) bySourceImage.set(d.source_image, []);
    bySourceImage.get(d.source_image).push(d);
  }

  const entries = Array.from(bySourceImage.entries());

  if (entries.length === 0) {
    return <p className="empty-note">No model evidence recorded for this location.</p>;
  }

  return (
    <div className="evidence-gallery">
      {entries.map(([sourceImage, detections]) => {
        const submitted = resolveSubmittedImage(submittedImages, sourceImage);
        if (!submitted) {
          // Backend referenced an image we can't resolve back to a browser
          // preview (shouldn't normally happen) -- don't hide the evidence,
          // just skip the image render.
          return null;
        }
        return (
          <BBoxImage
            key={sourceImage}
            previewUrl={submitted.previewUrl}
            filename={submitted.file.name}
            detections={detections}
          />
        );
      })}
    </div>
  );
}

// imageMatch.js
//
// The server wrapper (api/server.py) saves each uploaded image as
// "img_{index}_{name}.{ext}" in the order it was submitted. We rely on that
// naming convention -- not on re-deriving anything the backend computed --
// purely to show the original browser-side image (with its bbox overlay)
// next to the backend's evidence for it.

export function indexFromSourceImage(sourceImagePath) {
  if (!sourceImagePath) return null;
  const basename = sourceImagePath.split("/").pop().split("\\").pop();
  const match = basename.match(/^img_(\d+)_/);
  if (!match) return null;
  return parseInt(match[1], 10);
}

export function resolveSubmittedImage(submittedImages, sourceImagePath) {
  const idx = indexFromSourceImage(sourceImagePath);
  if (idx === null || !submittedImages[idx]) return null;
  return submittedImages[idx];
}

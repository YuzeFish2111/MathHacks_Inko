// Rotating the photo in the browser, before upload.
// The backend receives an already-upright photo, so cornerPointsPx and every overlay coordinate
// simply refer to the uploaded (rotated) image; no API change is needed.

import type { PointPx } from "../types/analysis";

const JPEG_QUALITY = 0.92;

/** Normalise any number of clockwise quarter turns to 0, 1, 2 or 3. */
export function normalizeQuarterTurns(quarterTurns: number): 0 | 1 | 2 | 3 {
  return (((Math.round(quarterTurns) % 4) + 4) % 4) as 0 | 1 | 2 | 3;
}

/**
 * Return a copy of the photo turned clockwise by quarterTurns x 90 degrees.
 *
 * Always rotate the ORIGINAL file by the total number of turns (not the previous result again),
 * so the photo is re-compressed only once however many times the button is pressed.
 * 0 turns returns the original file untouched.
 */
export async function rotateImageFile(originalFile: File, quarterTurns: number): Promise<File> {
  const turns = normalizeQuarterTurns(quarterTurns);
  if (turns === 0) {
    return originalFile;
  }

  // "from-image" applies the phone's EXIF orientation first, matching what the backend sees
  const bitmap = await createImageBitmap(originalFile, { imageOrientation: "from-image" });
  const isSideways = turns % 2 === 1;
  const canvas = document.createElement("canvas");
  canvas.width = isSideways ? bitmap.height : bitmap.width;
  canvas.height = isSideways ? bitmap.width : bitmap.height;

  const context = canvas.getContext("2d");
  if (!context) {
    bitmap.close();
    throw new Error("This browser can't rotate images.");
  }
  // Rotate about the canvas centre, then draw the photo centred on that point
  context.translate(canvas.width / 2, canvas.height / 2);
  context.rotate((turns * Math.PI) / 2);
  context.drawImage(bitmap, -bitmap.width / 2, -bitmap.height / 2);
  bitmap.close();

  // Keep PNGs lossless; everything else (JPEG, HEIC, WebP) becomes JPEG, which the backend accepts
  const outputType = originalFile.type === "image/png" ? "image/png" : "image/jpeg";
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, outputType, JPEG_QUALITY));
  if (!blob) {
    throw new Error("Couldn't create the rotated photo.");
  }
  const extension = outputType === "image/png" ? "png" : "jpg";
  const baseName = originalFile.name.replace(/\.[^.]+$/, "") || "photo";
  return new File([blob], `${baseName}-rotated.${extension}`, { type: outputType });
}

/**
 * Move page corners along with a 90-degree clockwise turn of an image widthPx x heightPx.
 *
 * A point (x, y) lands at (heightPx - y, x). The order is shifted too, so it stays
 * top-left, top-right, bottom-right, bottom-left: the old bottom-left becomes the new top-left.
 */
export function rotateCornerPointsClockwise(
  cornerPointsPx: [PointPx, PointPx, PointPx, PointPx],
  widthPx: number,
  heightPx: number,
): [PointPx, PointPx, PointPx, PointPx] {
  const turned = cornerPointsPx.map(([x, y]): PointPx => [heightPx - y, x]);
  const [topLeft, topRight, bottomRight, bottomLeft] = turned;
  return [bottomLeft, topLeft, topRight, bottomRight];
}

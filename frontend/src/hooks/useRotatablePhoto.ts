// State for the preview/crop screen: the chosen photo, how far it has been turned, and a preview URL.

import { useCallback, useEffect, useState } from "react";

import { normalizeQuarterTurns, rotateImageFile } from "../utils/rotateImage";

export interface RotatablePhoto {
  /** The photo to upload as imageFile (already rotated), or null before one is chosen. */
  photo: File | null;
  /** Object URL for an <img> preview of `photo`. */
  previewUrl: string | null;
  /** Clockwise quarter turns applied so far: 0, 1, 2 or 3. */
  quarterTurns: 0 | 1 | 2 | 3;
  isRotating: boolean;
  rotationError: string | null;
  /** Turn the photo a further 90 degrees clockwise. */
  rotateClockwise: () => Promise<void>;
}

export function useRotatablePhoto(originalFile: File | null): RotatablePhoto {
  const [photo, setPhoto] = useState<File | null>(originalFile);
  const [quarterTurns, setQuarterTurns] = useState<0 | 1 | 2 | 3>(0);
  const [isRotating, setIsRotating] = useState(false);
  const [rotationError, setRotationError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  // A newly chosen photo starts unrotated
  useEffect(() => {
    setPhoto(originalFile);
    setQuarterTurns(0);
    setRotationError(null);
  }, [originalFile]);

  // Make a preview URL for the current photo, and free the old one when it changes
  useEffect(() => {
    if (!photo) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(photo);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  const rotateClockwise = useCallback(async () => {
    if (!originalFile || isRotating) {
      return;
    }
    const nextQuarterTurns = normalizeQuarterTurns(quarterTurns + 1);
    setIsRotating(true);
    setRotationError(null);
    try {
      // Rotate the original by the total, so repeated presses don't lose quality
      setPhoto(await rotateImageFile(originalFile, nextQuarterTurns));
      setQuarterTurns(nextQuarterTurns);
    } catch (error) {
      setRotationError(error instanceof Error ? error.message : "Couldn't rotate the photo.");
    } finally {
      setIsRotating(false);
    }
  }, [originalFile, isRotating, quarterTurns]);

  return { photo, previewUrl, quarterTurns, isRotating, rotationError, rotateClockwise };
}

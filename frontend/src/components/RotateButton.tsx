// "Rotate 90°" button for the preview/crop screen. Pair it with useRotatablePhoto:
//
//   const { photo, previewUrl, isRotating, rotationError, rotateClockwise } = useRotatablePhoto(chosenFile);
//   <img src={previewUrl ?? undefined} alt="Your handwriting photo" />
//   <RotateButton onRotate={rotateClockwise} isRotating={isRotating} errorMessage={rotationError} />
//   ...then upload `photo` as imageFile.
//
// If the user has already placed page corners, either clear them on rotate or move them with
// rotateCornerPointsClockwise (utils/rotateImage.ts), since cornerPointsPx are in the photo's pixels.

export interface RotateButtonProps {
  onRotate: () => void;
  isRotating?: boolean;
  disabled?: boolean;
  errorMessage?: string | null;
  className?: string;
}

export function RotateButton({ onRotate, isRotating = false, disabled = false, errorMessage = null,
                               className }: RotateButtonProps) {
  return (
    <div className={className}>
      <button
        type="button"
        onClick={onRotate}
        disabled={disabled || isRotating}
        aria-label="Rotate photo 90 degrees clockwise"
        aria-busy={isRotating}
        style={{ minHeight: 44, minWidth: 44, padding: "8px 16px", fontSize: 16 }}    // easy to tap on a phone
      >
        <span aria-hidden="true">↻</span> {isRotating ? "Rotating…" : "Rotate 90°"}
      </button>
      {errorMessage && <p role="alert">{errorMessage}</p>}
    </div>
  );
}

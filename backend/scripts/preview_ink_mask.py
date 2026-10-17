"""Debug tool: show the ink mask for one image.

Run from the backend/ folder:
    python -m scripts.preview_ink_mask ../data/handwriting3.png

Needs matplotlib (pip install matplotlib); the API itself does not.
"""
import sys

import cv2
import matplotlib.pyplot as plt
import numpy as np

from app.image_pipeline import (load_image, to_grayscale, resize_to_width,
                                threshold_ink, remove_small_components)


def main(imagePath: str) -> None:
    originalImage = load_image(imagePath)
    grayscaleImage = resize_to_width(to_grayscale(originalImage))
    thresholdedMask = threshold_ink(grayscaleImage)
    inkMask = remove_small_components(thresholdedMask)
    inkMatrix = (inkMask > 0).astype(np.uint8)    # 0/1 version for printing

    print("Original dimensions:", originalImage.shape)
    print("Processed dimensions:", inkMatrix.shape)
    print("Resize factor:", grayscaleImage.shape[1] / originalImage.shape[1])
    print("Unique values:", np.unique(inkMatrix))
    print("Foreground pixel count:", int(inkMatrix.sum()))
    print("Matrix preview:")
    print(inkMatrix[:15, :30])

    plt.figure(figsize=(15, 5))
    panels = [
        (cv2.cvtColor(originalImage, cv2.COLOR_BGR2RGB), "Original Image"),
        (thresholdedMask, "Thresholded Image"),
        (inkMask, "Cleaned Ink Mask"),
    ]
    for panelIndex, (panelImage, panelTitle) in enumerate(panels, start=1):
        plt.subplot(1, 3, panelIndex)
        plt.imshow(panelImage, cmap="gray")
        plt.title(panelTitle)
        plt.axis("off")
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m scripts.preview_ink_mask <image path>")
    main(sys.argv[1])

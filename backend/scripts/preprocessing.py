#note: this is a duplicated copy of something that already exists
#do not delete for record keeping purposes
#__________________________________________________________________


# """Load a handwriting photo and turn it into a clean 0/1 ink matrix.

# Run from the backend/ folder:
#     python scripts/preprocessing.py [image path]     (default: data/image0(37).heic at the project root)
# HEIC photos (iPhone) need:  pip install pillow-heif
# """
# import sys
# from pathlib import Path

# import cv2
# import numpy as np

# # Found from this file's location, so it works from any folder
# PROJECT_ROOT = Path(__file__).resolve().parents[2]
# DEFAULT_IMAGE_PATH = str(PROJECT_ROOT / "data" / "image0(37).heic")


# # STEP 1: Read image (any format OpenCV reads, plus HEIC through pillow-heif)
# def load_photo(path):
#     if not Path(path).exists():
#         raise FileNotFoundError(f"Could not find {path}")

#     if Path(path).suffix.lower() in (".heic", ".heif"):
#         try:
#             from pillow_heif import register_heif_opener
#         except ImportError:
#             raise ImportError("HEIC photos need pillow-heif: run  pip install pillow-heif") from None
#         from PIL import Image
#         register_heif_opener()
#         pil_img = Image.open(path).convert("RGB")
#         return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

#     img = cv2.imread(path)
#     if img is None:
#         raise ValueError(f"Could not open {path} as an image")
#     return img


# def preprocess(img, target_width=1000, block_size=31, C=10, min_area=5):
#     """Return (gray, binary, matrix): resized grayscale, thresholded image, cleaned 0/1 matrix."""
#     # STEP 2: Convert to grayscale
#     gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

#     # STEP 3: Resize grayscale image
#     original_height, original_width = gray.shape
#     resize_factor = target_width / original_width
#     target_height = max(1, round(original_height * resize_factor))
#     interpolation = cv2.INTER_AREA if resize_factor < 1 else cv2.INTER_LINEAR
#     gray = cv2.resize(gray, (target_width, target_height), interpolation=interpolation)

#     # STEP 4: Reduce small intensity variations
#     blur = cv2.GaussianBlur(gray, (3, 3), 0)

#     # STEP 5: Adaptive thresholding
#     binary = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
#                                    cv2.THRESH_BINARY_INV, block_size, C)

#     # STEP 6: Remove tiny connected components
#     count, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
#     keep = stats[:, cv2.CC_STAT_AREA] >= min_area
#     keep[0] = False                                  # label 0 is the background
#     clean = np.where(keep[labels], 255, 0).astype(np.uint8)

#     # STEP 7: Convert to a 0/1 matrix
#     matrix = (clean > 0).astype(np.uint8)
#     return gray, binary, matrix


# def main(path):
#     import matplotlib.pyplot as plt

#     img = load_photo(path)
#     gray, binary, matrix = preprocess(img)

#     # STEP 8: Print information
#     print("Original dimensions:", img.shape)
#     print("Processed dimensions:", matrix.shape)
#     print("Resize factor:", gray.shape[1] / img.shape[1])
#     print("Unique values:", np.unique(matrix))
#     print("Foreground pixel count:", np.sum(matrix))
#     print("Matrix preview:")
#     print(matrix[:15, :30])

#     # STEP 9: Display results
#     plt.figure(figsize=(15, 5))
#     for index, (image, title) in enumerate([(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), "Original Image"),
#                                             (binary, "Thresholded Image"),
#                                             (matrix, "Cleaned Binary Matrix")], start=1):
#         plt.subplot(1, 3, index)
#         plt.imshow(image, cmap="gray")
#         plt.title(title)
#         plt.axis("off")
#     plt.tight_layout()
#     plt.show()


# if __name__ == "__main__":
#     main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IMAGE_PATH)

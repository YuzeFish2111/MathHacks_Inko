import cv2
import easyocr
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from pillow_heif import register_heif_opener

# STEP 1: Read image
register_heif_opener()
pil_img = Image.open("data/image0(37).heic").convert("RGB")
img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

if img is None:
    raise FileNotFoundError("Could not find handwriting.png")

# STEP 2: Convert to grayscale
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# STEP 3: Resize grayscale image
original_height, original_width = gray.shape

target_width = 1000
resize_factor = target_width / original_width
target_height = max(1, round(original_height * resize_factor))

if resize_factor < 1:
    interpolation = cv2.INTER_AREA
else:
    interpolation = cv2.INTER_LINEAR

gray = cv2.resize(
    gray,
    (target_width, target_height),
    interpolation=interpolation
)

# Optional physical scale:
# Only valid for a full, straightened page of known width.
page_width_mm = None

if page_width_mm is not None:
    scale_mm_per_px = page_width_mm / gray.shape[1]
else:
    scale_mm_per_px = None

# STEP 4: Reduce small intensity variations
blur = cv2.GaussianBlur(gray, (3, 3), 0)

# STEP 5: Adaptive thresholding
block_size = 31
C = 10

binary = cv2.adaptiveThreshold(
    blur,
    255,
    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
    cv2.THRESH_BINARY_INV,
    block_size,
    C
)

# STEP 6: Remove tiny connected components
min_area = 5

count, labels, stats, centroids = (
    cv2.connectedComponentsWithStats(
        binary,
        connectivity=8
    )
)

clean = np.zeros_like(binary)

for i in range(1, count):
    area = stats[i, cv2.CC_STAT_AREA]

    if area >= min_area:
        clean[labels == i] = 255

# STEP 7: Convert to a 0/1 matrix
matrix = (clean > 0).astype(np.uint8)

# STEP 8: Print information
print("Original dimensions:", img.shape)
print("Processed dimensions:", matrix.shape)
print("Resize factor:", resize_factor)
print("Unique values:", np.unique(matrix))
print("Foreground pixel count:", np.sum(matrix))

if scale_mm_per_px is not None:
    print("Millimetres per pixel:", scale_mm_per_px)

print("Matrix preview:")
print(matrix[:15, :30])

# STEP 9: Display results
plt.figure(figsize=(15, 5))

plt.subplot(1, 3, 1)
plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
plt.title("Original Image")
plt.axis("off")

plt.subplot(1, 3, 2)
plt.imshow(binary, cmap="gray")
plt.title("Thresholded Image")
plt.axis("off")

plt.subplot(1, 3, 3)
plt.imshow(matrix, cmap="gray")
plt.title("Cleaned Binary Matrix")
plt.axis("off")

plt.tight_layout()
plt.show()


import { MSG, MAX_UPLOAD_BYTES } from "../messages.js";
import { ApiError } from "../api.js";

const MAX_SIDE = 2000;             // match the server's model size
const RESIZE_OVER_BYTES = 2 * 1024 * 1024;
const OK_EXT = /\.(png|jpe?g|heic|heif|webp)$/i;

/** Hidden file inputs. Phones need two: `capture` opens the camera directly but hides
 *  the photo library, so "choose" and "camera" are separate buttons. */
export function createPickers(onFile) {
  const make = (capture) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*,.heic,.heif";
    if (capture) input.setAttribute("capture", "environment");
    input.className = "visually-hidden";
    input.tabIndex = -1;
    input.setAttribute("aria-hidden", "true");
    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      input.value = "";  // so picking the same file again still fires
      if (file) onFile(file);
    });
    document.body.append(input);
    return input;
  };
  const any = make(false);
  const camera = make(true);
  return { chooseFile: () => any.click(), openCamera: () => camera.click() };
}

/** Throws ApiError with the team's exact wording for a wrong type or a too-big file. */
export function checkFile(file) {
  const typeOk = (file.type || "").startsWith("image/") || OK_EXT.test(file.name || "");
  if (!typeOk || /^image\/(gif|svg)/.test(file.type)) throw new ApiError("wrong_file_type", MSG.wrong_file_type);
  if (file.size > MAX_UPLOAD_BYTES) throw new ApiError("file_too_big", MSG.file_too_big);
}

async function decode(blob) {
  const url = URL.createObjectURL(blob);
  const img = new Image();
  img.decoding = "async";
  img.src = url;
  try {
    await img.decode();
    return { img, url };
  } catch (e) {
    URL.revokeObjectURL(url);
    return null;  // e.g. HEIC in Chrome: the server converts it instead
  }
}

/** Shrink big photos before upload. Browsers draw images with their EXIF rotation
 *  applied, so the canvas copy is already upright. Returns what to send plus a
 *  local preview URL (null when this browser cannot show the format). */
export async function prepareImage(file) {
  checkFile(file);
  const decoded = await decode(file);
  if (!decoded) return { blob: file, name: file.name || "photo.heic", previewUrl: null };
  const { img, url } = decoded;
  const w = img.naturalWidth, hgt = img.naturalHeight;
  if (Math.max(w, hgt) <= MAX_SIDE && file.size <= RESIZE_OVER_BYTES) {
    return { blob: file, name: file.name || "photo.jpg", previewUrl: url };
  }
  const scale = Math.min(1, MAX_SIDE / Math.max(w, hgt));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(hgt * scale);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  URL.revokeObjectURL(url);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
  if (!blob) return { blob: file, name: file.name || "photo.jpg", previewUrl: null };
  return { blob, name: "photo.jpg", previewUrl: URL.createObjectURL(blob) };
}

export async function exampleFile() {
  const res = await fetch("img/example.jpg");
  if (!res.ok) throw new ApiError("server_down", MSG.server_down);
  const blob = await res.blob();
  return new File([blob], "example.jpg", { type: "image/jpeg" });
}

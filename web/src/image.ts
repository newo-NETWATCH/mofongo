// S3 only accepts image/jpeg up to 10 MB (api/openapi.yaml, POST /items). Convert in the browser.

export const MAX_PHOTO_BYTES = 10 * 1024 * 1024;

/** Re-encode any browser-readable image as JPEG, shrinking the long side to maxSide. */
export async function convertToJpeg(file: File, maxSide = 2048, quality = 0.85): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  try {
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("This browser cannot process images.");
    ctx.fillStyle = "#fff"; // JPEG has no alpha
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", quality),
    );
    if (!blob) throw new Error("The photo could not be converted to JPEG.");
    if (blob.size > MAX_PHOTO_BYTES) throw new Error("The photo is still over 10 MB. Pick a smaller one.");
    return blob;
  } finally {
    bitmap.close();
  }
}

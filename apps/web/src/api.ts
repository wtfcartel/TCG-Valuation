const TOKEN_KEY = "cardcore.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable — session-only */
  }
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T = any>(method: string, path: string, body?: unknown): Promise<T> {
  const token = getToken();
  const res = await fetch(path, {
    method,
    headers: {
      ...(body !== undefined ? { "content-type": "application/json" } : {}),
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && token) {
    setToken(null);
    location.reload();
  }
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) throw new ApiError(res.status, data?.message ?? `Request failed (${res.status})`);
  return data as T;
}

export async function download(path: string, filename: string): Promise<void> {
  const res = await fetch(path, { headers: { authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new ApiError(res.status, "Download failed");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Downscale a photo in the browser (longest side ≤ 2400 px, JPEG) so uploads stay well under serverless
 * request limits (4.5 MB on Vercel). Falls back to the original file if the browser cannot decode it.
 */
export async function shrinkImage(file: File, maxSide = 2400, quality = 0.88): Promise<Blob> {
  if (file.size < 1.5 * 1024 * 1024 && file.type === "image/jpeg") return file;
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
    return blob && blob.size < file.size ? blob : file;
  } catch {
    return file;
  }
}

/** Remove scripts, styles and other non-content markup from a saved page before uploading it. */
export function stripSavedPage(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  doc.querySelectorAll("script, style, noscript, svg, iframe, link, meta, template").forEach((el) => el.remove());
  doc.querySelectorAll("*").forEach((el) => {
    for (const attr of [...el.attributes]) if (!["class", "href", "id", "data-listingid"].includes(attr.name)) el.removeAttribute(attr.name);
  });
  return `<!doctype html><html><body>${doc.body.innerHTML}</body></html>`;
}

export async function uploadPhoto(assetId: string, file: File): Promise<void> {
  const form = new FormData();
  const image = await shrinkImage(file);
  form.append("file", image, image === file ? file.name : file.name.replace(/\.[^.]+$/, "") + ".jpg");
  const res = await fetch(`/api/assets/${assetId}/photos`, { method: "POST", headers: { authorization: `Bearer ${getToken()}` }, body: form });
  if (!res.ok) throw new ApiError(res.status, (await res.json()).message);
}

export async function photoUrl(photoId: string): Promise<string> {
  const res = await fetch(`/api/photos/${photoId}`, { headers: { authorization: `Bearer ${getToken()}` } });
  return URL.createObjectURL(await res.blob());
}

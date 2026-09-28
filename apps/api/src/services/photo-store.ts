import { createReadStream } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join, resolve, sep } from "node:path";
import { Readable } from "node:stream";
import type { ReadableStream as WebReadableStream } from "node:stream/web";

/** Where user photographs live. Keys are generated server-side (`<assetId>/<uuid>`), never user-supplied. */
export interface PhotoStore {
  readonly kind: string;
  put(key: string, data: Buffer, contentType: string): Promise<void>;
  get(key: string): Promise<Readable>;
}

export class LocalPhotoStore implements PhotoStore {
  readonly kind = "local";
  private readonly root: string;
  constructor(root: string) {
    this.root = resolve(root);
  }

  private path(key: string): string {
    const p = resolve(join(this.root, key));
    if (!p.startsWith(this.root + sep)) throw new Error("Invalid photo key");
    return p;
  }

  async put(key: string, data: Buffer, _contentType?: string): Promise<void> {
    const p = this.path(key);
    await mkdir(dirname(p), { recursive: true });
    await writeFile(p, data);
  }

  async get(key: string): Promise<Readable> {
    return createReadStream(this.path(key));
  }
}

/**
 * Vercel Blob private store: photos are never publicly addressable; they are streamed through the
 * authenticated /api/photos/:id route. On Vercel the SDK authenticates with the project's OIDC token
 * (or BLOB_READ_WRITE_TOKEN).
 */
export class VercelBlobPhotoStore implements PhotoStore {
  readonly kind = "vercel-blob";

  async put(key: string, data: Buffer, contentType: string): Promise<void> {
    const { put } = await import("@vercel/blob");
    await put(`photos/${key}`, data, { access: "private", contentType, addRandomSuffix: false, allowOverwrite: false });
  }

  async get(key: string): Promise<Readable> {
    const { get } = await import("@vercel/blob");
    const res = await get(`photos/${key}`, { access: "private" });
    if (!res || res.statusCode !== 200) throw new Error("Photo not found in blob store");
    return Readable.fromWeb(res.stream as unknown as WebReadableStream<Uint8Array>);
  }
}

export function createPhotoStore(config: { photoStorage: "local" | "vercel-blob"; photoStorageDir: string }): PhotoStore {
  return config.photoStorage === "vercel-blob" ? new VercelBlobPhotoStore() : new LocalPhotoStore(config.photoStorageDir);
}

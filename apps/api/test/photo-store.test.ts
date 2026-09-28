import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { createPhotoStore, LocalPhotoStore, VercelBlobPhotoStore } from "../src/services/photo-store.js";

async function read(stream: NodeJS.ReadableStream): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const c of stream) chunks.push(Buffer.from(c as Buffer));
  return Buffer.concat(chunks).toString();
}

describe("photo stores", () => {
  it("stores and streams photos on local disk and refuses keys outside its root", async () => {
    const store = new LocalPhotoStore(await mkdtemp(join(tmpdir(), "cc-photos-")));
    await store.put("asset-1/photo-1", Buffer.from("jpeg-bytes"), "image/jpeg");
    expect(await read(await store.get("asset-1/photo-1"))).toBe("jpeg-bytes");
    await expect(store.put("../escape", Buffer.from("x"), "image/jpeg")).rejects.toThrow(/Invalid photo key/);
  });

  it("selects private Vercel Blob when configured", () => {
    expect(createPhotoStore({ photoStorage: "vercel-blob", photoStorageDir: "/tmp" })).toBeInstanceOf(VercelBlobPhotoStore);
    expect(createPhotoStore({ photoStorage: "local", photoStorageDir: "/tmp" })).toBeInstanceOf(LocalPhotoStore);
  });
});

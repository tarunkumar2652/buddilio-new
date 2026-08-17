import { api } from "@/lib/api";

export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
const DIRECT_LIMIT = 4 * 1024 * 1024;

export const prettySize = (n) =>
  n >= 1024 * 1024 ? `${(n / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;

// Small files go in one request; anything bigger is chunked so the proxy can't truncate it.
export async function uploadFile(file, onProgress) {
  if (file.size > MAX_UPLOAD_BYTES) throw new Error("Files must be under 25MB.");

  if (file.size <= DIRECT_LIMIT) {
    const form = new FormData();
    form.append("file", file);
    const { data } = await api.post("/uploads/file", form, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (e) => e.total && onProgress?.(Math.round((e.loaded / e.total) * 100)),
    });
    onProgress?.(100);
    return data;
  }

  const { data: init } = await api.post("/uploads/chunk/init", {
    filename: file.name, size: file.size, content_type: file.type || "",
  });
  const size = init.chunk_size;
  const total = Math.ceil(file.size / size);
  for (let i = 0; i < total; i++) {
    const form = new FormData();
    form.append("upload_id", init.upload_id);
    form.append("index", String(i));
    form.append("chunk", file.slice(i * size, (i + 1) * size), file.name);
    await api.post("/uploads/chunk/part", form, { headers: { "Content-Type": "multipart/form-data" } });
    onProgress?.(Math.round(((i + 1) / total) * 95));
  }
  const form = new FormData();
  form.append("upload_id", init.upload_id);
  const { data } = await api.post("/uploads/chunk/complete", form,
    { headers: { "Content-Type": "multipart/form-data" } });
  onProgress?.(100);
  return data;
}

import { apiUrl, fetchWithWakeup } from "./base";

export interface TechDedupResult {
  blob: Blob;
  filename: string;
  initialRows: number;
  finalRows: number;
  removedRows: number;
}

function filenameFromContentDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const match = header.match(/filename="?([^";]+)"?/);
  return match ? match[1] : fallback;
}

export async function processTechDedup(
  file: File,
  onWaking?: (waking: boolean) => void
): Promise<TechDedupResult> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetchWithWakeup(
    apiUrl("/api/tech-dedup/process"),
    { method: "POST", body: formData },
    onWaking
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? "Запрос не удался");
  }
  const blob = await res.blob();
  const filename = filenameFromContentDisposition(
    res.headers.get("Content-Disposition"),
    file.name.replace(/\.xlsx?$/i, "") + "_cleaned.xlsx"
  );
  return {
    blob,
    filename,
    initialRows: Number(res.headers.get("X-Initial-Rows") ?? 0),
    finalRows: Number(res.headers.get("X-Final-Rows") ?? 0),
    removedRows: Number(res.headers.get("X-Removed-Rows") ?? 0),
  };
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

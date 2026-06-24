export interface BaggageRow {
  date: string;
  company: string;
  bag_status: string;
  flight: string;
}

interface ProcessResponse {
  rows: BaggageRow[];
  added: number;
  total: number;
}

async function parseErrorOrJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? "Запрос не удался");
  }
  return res.json();
}

export async function fetchCurrent(): Promise<BaggageRow[]> {
  const res = await fetch("/api/baggage-norm/current");
  const data = await parseErrorOrJson<{ rows: BaggageRow[] }>(res);
  return data.rows;
}

export async function uploadWeeklyFile(file: File): Promise<ProcessResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch("/api/baggage-norm/process", { method: "POST", body: formData });
  return parseErrorOrJson<ProcessResponse>(res);
}

export function downloadDatalensCsv() {
  window.location.href = "/api/baggage-norm/download";
}

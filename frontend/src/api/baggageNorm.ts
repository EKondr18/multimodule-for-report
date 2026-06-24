import { apiUrl, parseErrorOrJson } from "./base";

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

export async function fetchCurrent(): Promise<BaggageRow[]> {
  const res = await fetch(apiUrl("/api/baggage-norm/current"));
  const data = await parseErrorOrJson<{ rows: BaggageRow[] }>(res);
  return data.rows;
}

export async function uploadWeeklyFile(file: File): Promise<ProcessResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(apiUrl("/api/baggage-norm/process"), { method: "POST", body: formData });
  return parseErrorOrJson<ProcessResponse>(res);
}

export function downloadDatalensCsv() {
  window.location.href = apiUrl("/api/baggage-norm/download");
}

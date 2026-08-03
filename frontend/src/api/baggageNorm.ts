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
  preview_days: number;
}

export interface CurrentResponse {
  rows: BaggageRow[];
  total: number;
  preview_days: number;
}

export async function fetchCurrent(signal?: AbortSignal): Promise<CurrentResponse> {
  const res = await fetch(apiUrl("/api/baggage-norm/current"), { signal });
  return parseErrorOrJson<CurrentResponse>(res);
}

export async function uploadWeeklyFile(file: File): Promise<ProcessResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(apiUrl("/api/baggage-norm/process"), { method: "POST", body: formData });
  return parseErrorOrJson<ProcessResponse>(res);
}

export function downloadDatalensCsv(startDate?: string, endDate?: string) {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const query = params.toString();
  window.location.href = apiUrl(`/api/baggage-norm/download${query ? `?${query}` : ""}`);
}

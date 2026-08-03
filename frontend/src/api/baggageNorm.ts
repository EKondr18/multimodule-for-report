import { apiUrl, fetchWithWakeup, parseErrorOrJson } from "./base";

interface ProcessResponse {
  added: number;
  months: string;
}

export async function uploadWeeklyFile(
  file: File,
  onWaking?: (waking: boolean) => void
): Promise<ProcessResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetchWithWakeup(
    apiUrl("/api/baggage-norm/process"),
    { method: "POST", body: formData },
    onWaking
  );
  return parseErrorOrJson<ProcessResponse>(res);
}

export function downloadDatalensCsv(startDate?: string, endDate?: string) {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const query = params.toString();
  window.location.href = apiUrl(`/api/baggage-norm/download${query ? `?${query}` : ""}`);
}

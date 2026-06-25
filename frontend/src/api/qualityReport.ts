import { apiUrl, parseErrorOrJson } from "./base";

export type Granularity = "week" | "month" | "quarter" | "year";

export interface SummaryTable {
  id: string;
  title: string;
  columns: string[];
  rows: Record<string, string | number>[];
}

interface ViolationsResponse {
  tables: SummaryTable[];
}

export async function fetchViolationsSummary(
  perronFile: File,
  avkFile: File,
  startDate: string,
  endDate: string,
  granularity: Granularity
): Promise<ViolationsResponse> {
  const formData = new FormData();
  formData.append("perron_file", perronFile);
  formData.append("avk_file", avkFile);
  formData.append("start_date", startDate);
  formData.append("end_date", endDate);
  formData.append("granularity", granularity);
  const res = await fetch(apiUrl("/api/quality-report/violations"), { method: "POST", body: formData });
  return parseErrorOrJson<ViolationsResponse>(res);
}

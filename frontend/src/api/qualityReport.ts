import { apiUrl, parseErrorOrJson } from "./base";

export type Granularity = "week" | "month" | "quarter" | "year";

export interface SummaryTable {
  id: string;
  title: string;
  columns: string[];
  rows: Record<string, string | number>[];
  message?: string;
}

interface SummaryResponse {
  tables: SummaryTable[];
}

export async function fetchQualitySummary(
  files: { perron?: File | null; avk?: File | null; grh?: File | null; lir?: File | null },
  startDate: string,
  endDate: string,
  granularity: Granularity
): Promise<SummaryResponse> {
  const formData = new FormData();
  if (files.perron) formData.append("perron_file", files.perron);
  if (files.avk) formData.append("avk_file", files.avk);
  if (files.grh) formData.append("grh_file", files.grh);
  if (files.lir) formData.append("lir_file", files.lir);
  formData.append("start_date", startDate);
  formData.append("end_date", endDate);
  formData.append("granularity", granularity);
  const res = await fetch(apiUrl("/api/quality-report/summary"), { method: "POST", body: formData });
  return parseErrorOrJson<SummaryResponse>(res);
}

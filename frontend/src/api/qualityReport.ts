import { apiUrl, fetchWithWakeup, parseErrorOrJson } from "./base";

export type Granularity = "week" | "month" | "quarter" | "year";

export interface RowGroup {
  details: Record<string, string | number>[];
  [key: string]: string | number | Record<string, string | number>[];
}

export interface SummaryTable {
  id: string;
  title: string;
  columns: string[];
  rows: Record<string, string | number>[];
  message?: string;
  span_columns?: number;
  row_groups?: RowGroup[];
}

interface SummaryResponse {
  tables: SummaryTable[];
}

export async function fetchQualitySummary(
  files: { perron?: File | null; avk?: File | null; grh?: File | null; lir?: File | null; pab?: File | null },
  startDate: string,
  endDate: string,
  granularity: Granularity,
  onWaking?: (waking: boolean) => void
): Promise<SummaryResponse> {
  const formData = new FormData();
  if (files.perron) formData.append("perron_file", files.perron);
  if (files.avk) formData.append("avk_file", files.avk);
  if (files.grh) formData.append("grh_file", files.grh);
  if (files.lir) formData.append("lir_file", files.lir);
  if (files.pab) formData.append("pab_file", files.pab);
  formData.append("start_date", startDate);
  formData.append("end_date", endDate);
  formData.append("granularity", granularity);
  const res = await fetchWithWakeup(
    apiUrl("/api/quality-report/summary"),
    { method: "POST", body: formData },
    onWaking
  );
  return parseErrorOrJson<SummaryResponse>(res);
}

export async function fetchMonthSummary(
  files: { perron?: File | null; avk?: File | null; appeals?: File | null; production?: File | null },
  startDate: string,
  endDate: string,
  granularity: Granularity,
  onWaking?: (waking: boolean) => void
): Promise<SummaryResponse> {
  const formData = new FormData();
  if (files.perron) formData.append("perron_file", files.perron);
  if (files.avk) formData.append("avk_file", files.avk);
  if (files.appeals) formData.append("appeals_file", files.appeals);
  if (files.production) formData.append("production_file", files.production);
  formData.append("start_date", startDate);
  formData.append("end_date", endDate);
  formData.append("granularity", granularity);
  const res = await fetchWithWakeup(
    apiUrl("/api/month-report/summary"),
    { method: "POST", body: formData },
    onWaking
  );
  return parseErrorOrJson<SummaryResponse>(res);
}

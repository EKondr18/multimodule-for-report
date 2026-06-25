import { apiUrl, parseErrorOrJson } from "./base";

export interface CommentRow {
  date: string;
  company: string;
  bag_status: string;
  flight: string;
  comment: string;
}

export interface TbsCommentRow {
  "Дата рейса": string;
  "Номер рейса": string;
  "Багаж с повреждением": number;
  "Багаж с признаками доступа к содержимому": number;
}

export type Station = "vko" | "tbs";

interface ProcessResponse {
  rows: CommentRow[];
  total: number;
  xlsx_base64: string;
}

interface TbsProcessResponse {
  rows: TbsCommentRow[];
  total: number;
  totals: Record<string, number>;
  xlsx_base64: string;
}

export async function processBaggageComments(
  normFile: File,
  eventsFile: File,
  station: "vko"
): Promise<ProcessResponse>;
export async function processBaggageComments(
  normFile: File,
  eventsFile: File,
  station: "tbs"
): Promise<TbsProcessResponse>;
export async function processBaggageComments(
  normFile: File,
  eventsFile: File,
  station: Station
): Promise<ProcessResponse | TbsProcessResponse> {
  const formData = new FormData();
  formData.append("norm_file", normFile);
  formData.append("events_file", eventsFile);
  formData.append("station", station);
  const res = await fetch(apiUrl("/api/baggage-comments/process"), { method: "POST", body: formData });
  return parseErrorOrJson<ProcessResponse | TbsProcessResponse>(res);
}

export function downloadXlsxBase64(base64: string, filename: string) {
  const byteChars = atob(base64);
  const byteNumbers = new Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) byteNumbers[i] = byteChars.charCodeAt(i);
  const blob = new Blob([new Uint8Array(byteNumbers)], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

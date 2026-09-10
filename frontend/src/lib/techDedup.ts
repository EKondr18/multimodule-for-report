// Обработка модуля «Удаление дубликатов по обслуживанию техники» — целиком
// в браузере, без обращения к бэкенду (у этого модуля нет своего сервера).
//
// Логика 1:1 повторяет то, что раньше делал backend/app/modules/tech_dedup:
// разбор поля «Заказ-наряд» вида «Заказ-наряд №00000000001 от 05.12.2024 /
// Закрыт» на номер/дату/статус, для каждого номера заказа-наряда оставляем
// только строки с самой свежей датой, а при совпадении дат — только строки с
// самым «весомым» статусом («Закрыт» > «Выполнен» > «В работе» > «Открыт»),
// и в конце убираем точные дубли среди оставшихся строк (сравнение без учёта
// текста самого заказа-наряда и нескольких полей, которые могут чуть
// отличаться в повторных выгрузках одной и той же строки).

import * as XLSX from "xlsx";

const ORDER_COLUMN = "Заказ-наряд";

const EXCLUDE_FROM_FINAL_DEDUP = new Set([
  ORDER_COLUMN,
  "Контрагенты",
  "Цена",
  "Сумма",
  "Автомобиль.Модель автомобиля",
]);

const NUMBER_RE = /(№\s*[\w\d-]+)/;
const DATE_RE = /(\d{2}\.\d{2}\.\d{4})/;

const STATUS_PRIORITY: [string, number][] = [
  ["закрыт", 1],
  ["выполнен", 2],
  ["в работе", 3],
  ["открыт", 4],
];

export interface TechDedupResult {
  blob: Blob;
  filename: string;
  initialRows: number;
  finalRows: number;
  removedRows: number;
}

type Row = Record<string, unknown>;

function extractPureNumber(raw: unknown): string | null {
  const text = raw == null ? "" : String(raw);
  if (text.trim() === "" || text.toLowerCase() === "nan") return null;
  const match = text.match(NUMBER_RE);
  if (match) return match[1];
  return text.split("/")[0].trim();
}

function extractDateText(raw: unknown): string | null {
  const text = raw == null ? "" : String(raw);
  const match = text.match(DATE_RE);
  return match ? match[1] : null;
}

function dateTextToComparable(dateText: string | null): number | null {
  if (!dateText) return null;
  const match = dateText.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  if (!match) return null;
  const [, dd, mm, yyyy] = match;
  return Number(yyyy) * 10000 + Number(mm) * 100 + Number(dd);
}

function statusPriority(raw: unknown): number {
  let text = (raw == null ? "" : String(raw)).toLowerCase();
  if (text.includes("/")) {
    text = text.split("/").pop() ?? "";
  }
  for (const [keyword, priority] of STATUS_PRIORITY) {
    if (text.includes(keyword)) return priority;
  }
  return 99;
}

function getHeaderRow(sheet: XLSX.WorkSheet): string[] {
  const ref = sheet["!ref"];
  if (!ref) return [];
  const range = XLSX.utils.decode_range(ref);
  const headers: string[] = [];
  for (let c = range.s.c; c <= range.e.c; c++) {
    const cell = sheet[XLSX.utils.encode_cell({ r: range.s.r, c })];
    headers.push(cell ? String(cell.v) : "");
  }
  return headers;
}

function pickDataSheet(workbook: XLSX.WorkBook): { sheetName: string; columns: string[] } {
  for (const name of workbook.SheetNames) {
    const columns = getHeaderRow(workbook.Sheets[name]);
    if (columns.includes(ORDER_COLUMN)) {
      return { sheetName: name, columns };
    }
  }
  throw new Error(`Не найден лист со столбцом «${ORDER_COLUMN}» — проверьте структуру файла`);
}

interface Enriched {
  idx: number;
  row: Row;
  orderNumber: string | null;
  dateNum: number | null;
  priority: number;
}

export async function removeDuplicates(file: File): Promise<TechDedupResult> {
  const buffer = await file.arrayBuffer();
  const workbook = XLSX.read(buffer, { type: "array" });
  const { sheetName, columns } = pickDataSheet(workbook);

  const rows: Row[] = XLSX.utils.sheet_to_json(workbook.Sheets[sheetName], { defval: null });
  if (!columns.includes(ORDER_COLUMN)) {
    throw new Error(`В файле нет столбца «${ORDER_COLUMN}»`);
  }

  const initialRows = rows.length;

  const enriched: Enriched[] = rows.map((row, idx) => {
    const raw = row[ORDER_COLUMN];
    return {
      idx,
      row,
      orderNumber: extractPureNumber(raw),
      dateNum: dateTextToComparable(extractDateText(raw)),
      priority: statusPriority(raw),
    };
  });

  // 1. Для каждого номера заказа-наряда оставляем только строки с самой
  // свежей датой (строки без распознанного номера не трогаем).
  const maxDateByOrder = new Map<string, number | null>();
  for (const e of enriched) {
    if (e.orderNumber == null) continue;
    if (!maxDateByOrder.has(e.orderNumber)) maxDateByOrder.set(e.orderNumber, null);
    if (e.dateNum != null) {
      const cur = maxDateByOrder.get(e.orderNumber)!;
      if (cur == null || e.dateNum > cur) maxDateByOrder.set(e.orderNumber, e.dateNum);
    }
  }
  const step1 = enriched.filter((e) => {
    if (e.orderNumber == null) return true;
    const maxDate = maxDateByOrder.get(e.orderNumber)!;
    if (maxDate == null) return true;
    return e.dateNum === maxDate;
  });

  // 2. Если на самую свежую дату оказалось несколько статусов — оставляем
  // только строки с самым «весомым» статусом.
  const minPriorityByOrder = new Map<string, number>();
  for (const e of step1) {
    if (e.orderNumber == null) continue;
    const cur = minPriorityByOrder.get(e.orderNumber);
    if (cur == null || e.priority < cur) minPriorityByOrder.set(e.orderNumber, e.priority);
  }
  const step2 = step1.filter((e) => {
    if (e.orderNumber == null) return true;
    const best = minPriorityByOrder.get(e.orderNumber);
    return best == null || e.priority === best;
  });

  // 3. Финальная зачистка точных дублей среди отфильтрованных строк —
  // сравниваем все столбцы, кроме исключённых, и при совпадении оставляем
  // последнее вхождение (как pandas drop_duplicates(keep="last")).
  const subsetCols = columns.filter((c) => !EXCLUDE_FROM_FINAL_DEDUP.has(c));
  const lastByKey = new Map<string, Enriched>();
  for (const e of step2) {
    const key = subsetCols.map((c) => JSON.stringify(e.row[c] ?? null)).join("");
    lastByKey.set(key, e);
  }
  const deduped = Array.from(lastByKey.values()).sort((a, b) => a.idx - b.idx);
  const finalRows = deduped.length;

  const outSheet = XLSX.utils.json_to_sheet(
    deduped.map((e) => e.row),
    { header: columns }
  );
  const outWorkbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(outWorkbook, outSheet, sheetName);
  const outArray = XLSX.write(outWorkbook, { bookType: "xlsx", type: "array" }) as ArrayBuffer;
  const blob = new Blob([outArray], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });

  const filename = file.name.replace(/\.xlsx?$/i, "") + "_cleaned.xlsx";

  return {
    blob,
    filename,
    initialRows,
    finalRows,
    removedRows: initialRows - finalRows,
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

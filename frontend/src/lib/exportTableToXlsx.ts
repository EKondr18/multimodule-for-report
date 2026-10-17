// Экспорт одной таблицы в .xlsx через SheetJS.
//
// ВАЖНО: `xlsx` — тяжёлая библиотека, которую мы уже используем в модуле
// Tech Dedup через ленивую загрузку (см. frontend/src/tabs.ts). Чтобы не
// раздувать основной бандл, здесь мы импортируем "xlsx" динамически,
// внутри функции, а не на верхнем уровне модуля. SummaryTable/FilterableTable
// импортируют только эту обёртку (без статической зависимости от xlsx),
// поэтому фактическая загрузка библиотеки происходит только по клику на
// кнопку "Экспорт в Excel" — Vite выносит её в отдельный chunk.

export type CellValue = string | number | undefined | null;

/**
 * Экспортирует переданные строки в .xlsx-файл и инициирует скачивание.
 *
 * @param filename   Имя файла (с расширением .xlsx)
 * @param headers    Заголовки столбцов (первая строка листа)
 * @param rows        Массив строк, каждая строка — массив значений в порядке headers
 * @param sheetName  Имя листа (по умолчанию "Данные")
 */
export async function exportRowsToXlsx(
  filename: string,
  headers: string[],
  rows: CellValue[][],
  sheetName = "Данные"
): Promise<void> {
  const XLSX = await import("xlsx");
  const aoa: (string | number)[][] = [
    headers,
    ...rows.map((row) => row.map((cell) => (cell == null ? "" : cell))),
  ];
  const worksheet = XLSX.utils.aoa_to_sheet(aoa);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, sheetName);
  XLSX.writeFile(workbook, filename);
}

/** Безопасное имя файла: убирает символы, недопустимые в большинстве ФС. */
export function sanitizeFilename(title: string): string {
  const cleaned = title.trim().replace(/[\\/:*?"<>|]+/g, "_");
  return cleaned || "table";
}

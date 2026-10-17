// Статистическая (не бизнес-специфичная!) эвристика для подсветки
// аномальных значений в таблицах отчётов.
//
// В приложении 40+ разных таблиц с совершенно разными колонками и смыслом
// значений — нет единого бизнес-правила "это значение плохое". Поэтому
// подсветка строится исключительно на статистике внутри одного столбца
// одной отображаемой таблицы: для каждого числового столбца считаем
// среднее и стандартное отклонение по видимым строкам и помечаем ячейки,
// значение которых отклоняется от среднего больше, чем на `thresholdStdDev`
// стандартных отклонений (z-score). Порог 2.0 — общепринятое "мягкое"
// значение для подобных эвристик (у нормального распределения это ~95%-й
// интервал), которое не требует знания природы метрики. Это сигнал уровня
// "обратите внимание", а не "ошибка".
//
// Эвристика намеренно консервативна:
//  - столбец должен состоять из чисел практически полностью (>=60% строк),
//    иначе статистика по нескольким случайным числам в текстовом столбце
//    будет шумом, а не сигналом;
//  - нужно минимум `minSamples` числовых значений, иначе z-score
//    статистически не имеет смысла;
//  - столбец с нулевым разбросом (все значения одинаковы) не помечается —
//    делить на std=0 нельзя, и выбросов там по определению нет;
//  - столбцы, похожие на идентификаторы/даты/номера/периоды (по названию),
//    исключаются — колонка "№ рейса" или "Дата" не является "трендовой
//    метрикой", и выброс в ней ничего не говорит о качестве данных.

export type CellValue = string | number | undefined | null;

export interface OutlierOptions {
  /** Порог в стандартных отклонениях от среднего (по умолчанию 2.0). */
  thresholdStdDev?: number;
  /** Минимальное количество числовых значений в столбце для анализа. */
  minSamples?: number;
  /** Минимальная доля строк столбца, которая должна быть числовой. */
  minNumericRatio?: number;
}

const IDENTIFIER_OR_DATE_PATTERN =
  /(^|[\s_()/-])(id|ид|№|номер|number|code|код|дата|date|период|period|год|year|месяц|month|квартал|quarter|неделя|week)([\s_()/-]|$)/i;

/** Пытается разобрать значение ячейки как число (включая "1 234,5"). */
function parseCellNumber(value: CellValue): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const normalized = trimmed.replace(/\s+/g, "").replace(",", ".");
  if (!/^-?\d+(\.\d+)?$/.test(normalized)) return null;
  return parseFloat(normalized);
}

/** Похож ли столбец (по названию) на идентификатор/дату/период. */
export function looksLikeIdentifierColumn(columnName: string): boolean {
  return IDENTIFIER_OR_DATE_PATTERN.test(columnName);
}

/**
 * Вычисляет множество "аномальных" ячеек для переданных строк.
 * Возвращает Set ключей вида `${rowIndex}:${columnKey}`.
 *
 * @param rows    строки таблицы; индекс в массиве используется как rowIndex в ключе
 * @param columns ключи столбцов, которые нужно анализировать (идентификаторы/даты лучше отфильтровать заранее через looksLikeIdentifierColumn)
 */
export function computeOutlierCells(
  rows: Record<string, CellValue>[],
  columns: string[],
  opts: OutlierOptions = {}
): Set<string> {
  const { thresholdStdDev = 2, minSamples = 5, minNumericRatio = 0.6 } = opts;
  const flagged = new Set<string>();
  if (rows.length === 0) return flagged;

  for (const col of columns) {
    if (looksLikeIdentifierColumn(col)) continue;

    const numericEntries: { idx: number; value: number }[] = [];
    rows.forEach((row, idx) => {
      const parsed = parseCellNumber(row[col]);
      if (parsed !== null) numericEntries.push({ idx, value: parsed });
    });

    if (numericEntries.length < minSamples) continue;
    if (numericEntries.length < rows.length * minNumericRatio) continue;

    const values = numericEntries.map((e) => e.value);
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length;
    const std = Math.sqrt(variance);
    if (std === 0) continue;

    for (const { idx, value } of numericEntries) {
      if (Math.abs(value - mean) / std > thresholdStdDev) {
        flagged.add(`${idx}:${col}`);
      }
    }
  }

  return flagged;
}

export function outlierKey(rowIndex: number, column: string): string {
  return `${rowIndex}:${column}`;
}

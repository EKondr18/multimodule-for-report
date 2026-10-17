import { useMemo, useState } from "react";
import { exportRowsToXlsx, sanitizeFilename } from "../lib/exportTableToXlsx";
import { computeOutlierCells, looksLikeIdentifierColumn, outlierKey } from "../lib/outliers";

interface Column {
  key: string;
  label: string;
}

interface Props {
  columns: Column[];
  rows: Record<string, string>[];
  pageSize?: number;
  totals?: Record<string, string | number>;
  /** См. SummaryTable — та же статистическая эвристика, включена по умолчанию. */
  highlightOutliers?: boolean;
  /** Заголовок таблицы, используется для имени файла при экспорте. */
  title?: string;
}

export default function FilterableTable({
  columns,
  rows,
  pageSize = 25,
  totals,
  highlightOutliers = true,
  title = "table",
}: Props) {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(0);
  const [exporting, setExporting] = useState(false);

  const uniqueValues = useMemo(() => {
    const result: Record<string, string[]> = {};
    for (const col of columns) {
      result[col.key] = Array.from(new Set(rows.map((r) => r[col.key]))).sort();
    }
    return result;
  }, [columns, rows]);

  const filtered = useMemo(() => {
    return rows.filter((row) =>
      columns.every((col) => {
        const value = filters[col.key];
        if (!value) return true;
        return row[col.key]?.toLowerCase().includes(value.toLowerCase());
      })
    );
  }, [rows, filters, columns]);

  const analyzedColumns = useMemo(
    () => columns.filter((c) => !looksLikeIdentifierColumn(c.key) && !looksLikeIdentifierColumn(c.label)).map((c) => c.key),
    [columns]
  );

  // Статистика считается по всему отфильтрованному набору (не только по
  // текущей странице) — так z-score не "прыгает" при переключении страниц.
  const outlierCells = useMemo(() => {
    if (!highlightOutliers) return new Set<string>();
    return computeOutlierCells(filtered, analyzedColumns);
  }, [filtered, analyzedColumns, highlightOutliers]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount - 1);
  const pageStart = currentPage * pageSize;
  const pageRows = filtered.slice(pageStart, pageStart + pageSize);

  const setFilter = (key: string, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(0);
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const exportRows = filtered.map((row) => columns.map((col) => row[col.key] ?? ""));
      await exportRowsToXlsx(
        `${sanitizeFilename(title)}.xlsx`,
        columns.map((c) => c.label),
        exportRows
      );
    } finally {
      setExporting(false);
    }
  };

  // См. SummaryTable — тот же non-color cue: `title` озвучивается
  // скринридерами и виден дальтоникам по фокусу/наведению, не только через
  // цвет фона/полосы.
  const isOutlier = (globalIdx: number, colKey: string) => outlierCells.has(outlierKey(globalIdx, colKey));
  const outlierClass = (globalIdx: number, colKey: string) =>
    isOutlier(globalIdx, colKey) ? "cell-outlier" : undefined;
  const outlierTitle = (globalIdx: number, colKey: string) =>
    isOutlier(globalIdx, colKey) ? "Статистический выброс: значение сильно отклоняется от среднего по столбцу" : undefined;

  return (
    <div>
      <div className="table-actions" style={{ marginBottom: 10, justifyContent: "flex-end", display: "flex" }}>
        <button className="btn btn-sm" onClick={handleExport} disabled={exporting || filtered.length === 0}>
          {exporting ? "Экспорт…" : "Экспорт в Excel"}
        </button>
      </div>
      <div className="table-scroll">
        <table className="preview">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.key}>{col.label}</th>
              ))}
            </tr>
            <tr className="filters">
              {columns.map((col) => {
                const options = uniqueValues[col.key];
                const useSelect = options.length <= 30;
                return (
                  <th key={col.key}>
                    {useSelect ? (
                      <select
                        value={filters[col.key] ?? ""}
                        onChange={(e) => setFilter(col.key, e.target.value)}
                      >
                        <option value="">Все</option>
                        {options.map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        placeholder="Фильтр..."
                        value={filters[col.key] ?? ""}
                        onChange={(e) => setFilter(col.key, e.target.value)}
                      />
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, idx) => (
              <tr key={idx}>
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={outlierClass(pageStart + idx, col.key)}
                    title={outlierTitle(pageStart + idx, col.key)}
                  >
                    {row[col.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          {totals && (
            <tfoot>
              <tr className="totals">
                {columns.map((col, idx) => (
                  <td key={col.key}>
                    {idx === 0 ? "Итого" : (totals[col.key] ?? "")}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
      <div className="pagination">
        <button
          className="btn"
          disabled={currentPage === 0}
          onClick={() => setPage(currentPage - 1)}
        >
          Назад
        </button>
        <span>
          Стр. {currentPage + 1} из {pageCount} ({filtered.length} строк из {rows.length})
        </span>
        <button
          className="btn"
          disabled={currentPage >= pageCount - 1}
          onClick={() => setPage(currentPage + 1)}
        >
          Вперёд
        </button>
      </div>
    </div>
  );
}

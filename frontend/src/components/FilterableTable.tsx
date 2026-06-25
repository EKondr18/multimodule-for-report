import { useMemo, useState } from "react";

interface Column {
  key: string;
  label: string;
}

interface Props {
  columns: Column[];
  rows: Record<string, string>[];
  pageSize?: number;
  totals?: Record<string, string | number>;
}

export default function FilterableTable({ columns, rows, pageSize = 25, totals }: Props) {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(0);

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

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount - 1);
  const pageRows = filtered.slice(currentPage * pageSize, (currentPage + 1) * pageSize);

  const setFilter = (key: string, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(0);
  };

  return (
    <div>
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
                <td key={col.key}>{row[col.key]}</td>
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

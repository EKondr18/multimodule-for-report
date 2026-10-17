import { useMemo, useState } from "react";
import { RowGroup, SummaryTable as SummaryTableData } from "../api/qualityReport";
import { exportRowsToXlsx, sanitizeFilename } from "../lib/exportTableToXlsx";
import { computeOutlierCells, looksLikeIdentifierColumn, outlierKey } from "../lib/outliers";

interface Props {
  table: SummaryTableData;
  /**
   * Статистическая подсветка числовых выбросов по столбцу (см.
   * frontend/src/lib/outliers.ts). Включена по умолчанию — это
   * безопасная, предметно-независимая эвристика. Отключать стоит для
   * таблиц, где каждая строка — это единичный инцидент, а не ряд
   * однородных измерений (например, построчный список нарушений), где
   * "разброс" ничего не говорит об аномалии.
   */
  highlightOutliers?: boolean;
}

function formatDisplay(value: string | number | undefined): string {
  if (typeof value === "number") {
    return value.toLocaleString("ru-RU");
  }
  return value != null ? String(value) : "";
}

export default function SummaryTable({ table, highlightOutliers = true }: Props) {
  const [copied, setCopied] = useState(false);
  const [exporting, setExporting] = useState(false);

  const spanCount = table.span_columns ?? 1;
  const spanCols = table.columns.slice(0, spanCount);
  const detailCols = table.columns.slice(spanCount);

  // Плоский список строк для экспорта/подсветки — одинаковый порядок для
  // простых и "сгруппированных" (row_groups) таблиц.
  const flatRows: Record<string, string | number | undefined>[] = useMemo(() => {
    if (!table.row_groups) return table.rows;
    const flat: Record<string, string | number | undefined>[] = [];
    for (const group of table.row_groups) {
      if (group.details.length === 0) {
        const row: Record<string, string | number | undefined> = {};
        spanCols.forEach((c) => (row[c] = group[c] as string | number));
        flat.push(row);
      } else {
        group.details.forEach((detail, i) => {
          const row: Record<string, string | number | undefined> = { ...detail };
          if (i === 0) spanCols.forEach((c) => (row[c] = group[c] as string | number));
          flat.push(row);
        });
      }
    }
    return flat;
  }, [table.row_groups, table.rows, spanCols]);

  const analyzedColumns = useMemo(
    () => table.columns.filter((c) => !looksLikeIdentifierColumn(c)),
    [table.columns]
  );

  const outlierCells = useMemo(() => {
    if (!highlightOutliers) return new Set<string>();
    return computeOutlierCells(flatRows, analyzedColumns);
  }, [flatRows, analyzedColumns, highlightOutliers]);

  const handleCopy = async () => {
    let lines: string[];
    if (table.row_groups) {
      lines = [table.columns.join("\t")];
      for (const group of table.row_groups) {
        if (group.details.length === 0) {
          lines.push([
            ...spanCols.map((c) => group[c] ?? ""),
            ...detailCols.map(() => ""),
          ].join("\t"));
        } else {
          group.details.forEach((detail, i) => {
            const spanVals = i === 0
              ? spanCols.map((c) => group[c] ?? "")
              : spanCols.map(() => "");
            lines.push([...spanVals, ...detailCols.map((c) => detail[c] ?? "")].join("\t"));
          });
        }
      }
    } else {
      lines = [
        table.columns.join("\t"),
        ...table.rows.map((row) => table.columns.map((col) => row[col] ?? "").join("\t")),
      ];
    }
    await navigator.clipboard.writeText(lines.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const rows = flatRows.map((row) => table.columns.map((col) => row[col] ?? ""));
      await exportRowsToXlsx(
        `${sanitizeFilename(table.title || table.id)}.xlsx`,
        table.columns,
        rows
      );
    } finally {
      setExporting(false);
    }
  };

  if (table.message) {
    return (
      <div style={{ marginBottom: 24 }}>
        <h4 style={{ margin: 0, marginBottom: 8 }}>{table.title}</h4>
        <div className="status-msg">{table.message}</div>
      </div>
    );
  }

  const outlierClass = (rowIdx: number, col: string) =>
    outlierCells.has(outlierKey(rowIdx, col)) ? "cell-outlier" : undefined;

  const renderGroupedBody = (groups: RowGroup[]) => {
    let flatIdx = 0;
    return groups.flatMap((group, gi) => {
      if (group.details.length === 0) {
        const idx = flatIdx++;
        return [(
          <tr key={`${gi}-empty`}>
            {spanCols.map((col) => (
              <td key={col} className={outlierClass(idx, col)}>
                {formatDisplay(group[col] as string | number)}
              </td>
            ))}
            {detailCols.map((col) => <td key={col}></td>)}
          </tr>
        )];
      }
      return group.details.map((detail, di) => {
        const idx = flatIdx++;
        return (
          <tr key={`${gi}-${di}`}>
            {di === 0 && spanCols.map((col) => (
              <td key={col} rowSpan={group.details.length} className={outlierClass(idx, col)}>
                {formatDisplay(group[col] as string | number)}
              </td>
            ))}
            {detailCols.map((col) => (
              <td key={col} className={outlierClass(idx, col)}>
                {formatDisplay(detail[col])}
              </td>
            ))}
          </tr>
        );
      });
    });
  };

  return (
    <div style={{ marginBottom: 28 }}>
      <div className="summary-table-header">
        <span className="summary-table-title">{table.title}</span>
        <div className="table-actions">
          <button className="btn btn-sm" onClick={handleCopy}>
            {copied ? "✓ Скопировано" : "Копировать"}
          </button>
          <button className="btn btn-sm" onClick={handleExport} disabled={exporting}>
            {exporting ? "Экспорт…" : "Экспорт в Excel"}
          </button>
        </div>
      </div>
      <div className="table-scroll">
        <table className="preview">
          <thead>
            <tr>
              {table.columns.map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.row_groups
              ? renderGroupedBody(table.row_groups)
              : table.rows.map((row, idx) => (
                  <tr key={idx}>
                    {table.columns.map((col) => (
                      <td key={col} className={outlierClass(idx, col)}>
                        {formatDisplay(row[col])}
                      </td>
                    ))}
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

import { useState } from "react";
import { RowGroup, SummaryTable as SummaryTableData } from "../api/qualityReport";

interface Props {
  table: SummaryTableData;
}

function formatDisplay(value: string | number | undefined): string {
  if (typeof value === "number") {
    return value.toLocaleString("ru-RU");
  }
  return value != null ? String(value) : "";
}

export default function SummaryTable({ table }: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    let lines: string[];
    if (table.row_groups) {
      const spanCount = table.span_columns ?? 1;
      const spanCols = table.columns.slice(0, spanCount);
      const detailCols = table.columns.slice(spanCount);
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

  if (table.message) {
    return (
      <div style={{ marginBottom: 24 }}>
        <h4 style={{ margin: 0, marginBottom: 8 }}>{table.title}</h4>
        <div className="status-msg">{table.message}</div>
      </div>
    );
  }

  const renderGroupedBody = (groups: RowGroup[]) => {
    const spanCount = table.span_columns ?? 1;
    const spanCols = table.columns.slice(0, spanCount);
    const detailCols = table.columns.slice(spanCount);

    return groups.flatMap((group, gi) => {
      if (group.details.length === 0) {
        return [(
          <tr key={`${gi}-empty`}>
            {spanCols.map((col) => (
              <td key={col}>{formatDisplay(group[col] as string | number)}</td>
            ))}
            {detailCols.map((col) => <td key={col}></td>)}
          </tr>
        )];
      }
      return group.details.map((detail, di) => (
        <tr key={`${gi}-${di}`}>
          {di === 0 && spanCols.map((col) => (
            <td key={col} rowSpan={group.details.length}>
              {formatDisplay(group[col] as string | number)}
            </td>
          ))}
          {detailCols.map((col) => (
            <td key={col}>{formatDisplay(detail[col])}</td>
          ))}
        </tr>
      ));
    });
  };

  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
        <h4 style={{ margin: 0 }}>{table.title}</h4>
        <button className="btn" onClick={handleCopy}>
          {copied ? "Скопировано" : "Копировать"}
        </button>
      </div>
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
                    <td key={col}>{formatDisplay(row[col])}</td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  );
}

import { useState } from "react";
import { SummaryTable as SummaryTableData } from "../api/qualityReport";

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
    const lines = [
      table.columns.join("\t"),
      ...table.rows.map((row) => table.columns.map((col) => row[col] ?? "").join("\t")),
    ];
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
          {table.rows.map((row, idx) => (
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

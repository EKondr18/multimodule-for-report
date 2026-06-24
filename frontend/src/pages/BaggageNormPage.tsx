import { useEffect, useState } from "react";
import FileUpload from "../components/FileUpload";
import FilterableTable from "../components/FilterableTable";
import { BaggageRow, downloadDatalensCsv, fetchCurrent, uploadWeeklyFile } from "../api/baggageNorm";

const COLUMNS = [
  { key: "date", label: "Дата" },
  { key: "company", label: "Авиакомпания" },
  { key: "bag_status", label: "Статус выдачи" },
  { key: "flight", label: "Рейс" },
];

export default function BaggageNormPage() {
  const [rows, setRows] = useState<BaggageRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCurrent()
      .then(setRows)
      .catch((e) => setError(e.message));
  }, []);

  const handleFile = async (file: File) => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const result = await uploadWeeklyFile(file);
      setRows(result.rows);
      setMessage(`Добавлено ${result.added} строк, всего в архиве ${result.total}.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1>Норматив выдачи багажа</h1>

      <div className="card">
        <h3>1. Загрузить выгрузку BI МАВ за неделю (xlsx)</h3>
        <FileUpload onFile={handleFile} disabled={loading} />
        {loading && <div className="status-msg">Обработка файла и обновление архива в GitHub…</div>}
        {message && <div className="status-msg">{message}</div>}
        {error && <div className="status-msg error">{error}</div>}
      </div>

      <div className="card">
        <h3>2. Итоговый файл для DataLens</h3>
        <button className="btn" onClick={downloadDatalensCsv} disabled={rows.length === 0}>
          Скачать csv
        </button>
        <div style={{ marginTop: 16 }}>
          <FilterableTable columns={COLUMNS} rows={rows as unknown as Record<string, string>[]} />
        </div>
      </div>
    </div>
  );
}

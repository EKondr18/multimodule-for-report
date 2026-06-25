import { useState } from "react";
import FileUpload from "../components/FileUpload";
import FilterableTable from "../components/FilterableTable";
import { CommentRow, Station, downloadXlsxBase64, processBaggageComments } from "../api/baggageComments";

const COLUMNS = [
  { key: "date", label: "Дата" },
  { key: "company", label: "Авиакомпания" },
  { key: "bag_status", label: "Статус выдачи" },
  { key: "flight", label: "Рейс" },
  { key: "comment", label: "Комментарий" },
];

export default function BaggageCommentsPage() {
  const [station, setStation] = useState<Station>("vko");
  const [normFile, setNormFile] = useState<File | null>(null);
  const [eventsFile, setEventsFile] = useState<File | null>(null);
  const [rows, setRows] = useState<CommentRow[]>([]);
  const [xlsxBase64, setXlsxBase64] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const changeStation = (next: Station) => {
    setStation(next);
    setNormFile(null);
    setEventsFile(null);
    setRows([]);
    setXlsxBase64(null);
    setError(null);
  };

  const handleProcess = async () => {
    if (!normFile || !eventsFile) return;
    setLoading(true);
    setError(null);
    try {
      const result = await processBaggageComments(normFile, eventsFile, station);
      setRows(result.rows);
      setXlsxBase64(result.xlsx_base64);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1>Добавление комментариев по багажу</h1>

      <div className="card">
        <div className="station-switch">
          <button
            className={station === "vko" ? "btn active" : "btn"}
            onClick={() => changeStation("vko")}
          >
            VKO
          </button>
          <button
            className={station === "tbs" ? "btn active" : "btn"}
            onClick={() => changeStation("tbs")}
          >
            TBS
          </button>
        </div>
      </div>

      <div className="card">
        <h3>1. Норматив выдачи багажа (csv)</h3>
        <FileUpload
          accept=".csv"
          label="Перетащите csv-файл сюда или нажмите, чтобы выбрать"
          onFile={setNormFile}
          disabled={loading}
        />
        {normFile && <div className="status-msg">Выбран файл: {normFile.name}</div>}
      </div>

      <div className="card">
        <h3>2. События по выдаче (excel)</h3>
        <FileUpload
          accept=".xlsx,.xls"
          label="Перетащите xlsx-файл сюда или нажмите, чтобы выбрать"
          onFile={setEventsFile}
          disabled={loading}
        />
        {eventsFile && <div className="status-msg">Выбран файл: {eventsFile.name}</div>}
      </div>

      <div className="card">
        <button className="btn" onClick={handleProcess} disabled={!normFile || !eventsFile || loading}>
          Объединить
        </button>
        {loading && <div className="status-msg">Обработка файлов…</div>}
        {error && <div className="status-msg error">{error}</div>}
      </div>

      {rows.length > 0 && (
        <div className="card">
          <h3>3. Результат</h3>
          <button
            className="btn"
            onClick={() => xlsxBase64 && downloadXlsxBase64(xlsxBase64, `bagazh_kommentarii_${station}.xlsx`)}
          >
            Скачать excel
          </button>
          <div style={{ marginTop: 16 }}>
            <FilterableTable columns={COLUMNS} rows={rows as unknown as Record<string, string>[]} />
          </div>
        </div>
      )}
    </div>
  );
}

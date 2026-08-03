import { useState } from "react";
import FileUpload from "../components/FileUpload";
import FilterableTable from "../components/FilterableTable";
import {
  CommentRow,
  Station,
  TbsCommentRow,
  downloadXlsxBase64,
  processBaggageComments,
} from "../api/baggageComments";

const VKO_COLUMNS = [
  { key: "date", label: "Дата" },
  { key: "company", label: "Авиакомпания" },
  { key: "bag_status", label: "Статус выдачи" },
  { key: "flight", label: "Рейс" },
  { key: "comment", label: "Комментарий" },
];

const TBS_COLUMNS = [
  { key: "Дата рейса", label: "Дата рейса" },
  { key: "Номер рейса", label: "Номер рейса" },
  { key: "Багаж с повреждением", label: "Багаж с повреждением" },
  { key: "Багаж с признаками доступа к содержимому", label: "Багаж с признаками доступа к содержимому" },
];

export default function BaggageCommentsPage() {
  const [station, setStation] = useState<Station>("vko");
  const [normFile, setNormFile] = useState<File | null>(null);
  const [eventsFile, setEventsFile] = useState<File | null>(null);
  const [rows, setRows] = useState<(CommentRow | TbsCommentRow)[]>([]);
  const [totals, setTotals] = useState<Record<string, number> | undefined>(undefined);
  const [xlsxBase64, setXlsxBase64] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [waking, setWaking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const changeStation = (next: Station) => {
    setStation(next);
    setNormFile(null);
    setEventsFile(null);
    setRows([]);
    setTotals(undefined);
    setXlsxBase64(null);
    setError(null);
  };

  const handleProcess = async () => {
    if (!normFile || !eventsFile) return;
    setLoading(true);
    setError(null);
    try {
      if (station === "tbs") {
        const result = await processBaggageComments(normFile, eventsFile, "tbs", setWaking);
        setRows(result.rows);
        setTotals(result.totals);
        setXlsxBase64(result.xlsx_base64);
      } else {
        const result = await processBaggageComments(normFile, eventsFile, "vko", setWaking);
        setRows(result.rows);
        setTotals(undefined);
        setXlsxBase64(result.xlsx_base64);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
      setWaking(false);
    }
  };

  const columns = station === "tbs" ? TBS_COLUMNS : VKO_COLUMNS;
  const window1Title = station === "tbs" ? "Рейсы из TBS (прилет)" : "Норматив выдачи багажа (csv)";
  const window1Accept = station === "tbs" ? ".xlsx,.xls" : ".csv";
  const window2Title = station === "tbs" ? "События по багажу" : "События по выдаче (excel)";

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
        <h3>1. {window1Title}</h3>
        <FileUpload
          accept={window1Accept}
          label="Перетащите файл сюда или нажмите, чтобы выбрать"
          onFile={setNormFile}
          disabled={loading}
        />
        {normFile && <div className="status-msg">Выбран файл: {normFile.name}</div>}
      </div>

      <div className="card">
        <h3>2. {window2Title}</h3>
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
        {waking && <div className="status-msg">Сервер просыпается, подождите…</div>}
        {loading && !waking && <div className="status-msg">Обработка файлов…</div>}
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
            <FilterableTable
              columns={columns}
              rows={rows as unknown as Record<string, string>[]}
              totals={totals}
            />
          </div>
        </div>
      )}
    </div>
  );
}

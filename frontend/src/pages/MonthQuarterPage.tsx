import { useState } from "react";
import FileUpload from "../components/FileUpload";
import SummaryTable from "../components/SummaryTable";
import { SummaryTable as SummaryTableData, fetchMonthSummary } from "../api/qualityReport";

export default function MonthQuarterPage() {
  const [perronFile, setPerronFile] = useState<File | null>(null);
  const [avkFile, setAvkFile] = useState<File | null>(null);
  const [appealsFile, setAppealsFile] = useState<File | null>(null);
  const [productionFile, setProductionFile] = useState<File | null>(null);

  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [tables, setTables] = useState<SummaryTableData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => setTables([]);

  const handleBuild = async () => {
    if (!startDate || !endDate) return;
    setLoading(true);
    setError(null);
    try {
      const result = await fetchMonthSummary(
        { perron: perronFile, avk: avkFile, appeals: appealsFile, production: productionFile },
        startDate,
        endDate,
        "month"
      );
      setTables(result.tables);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1>Месяц / Квартал</h1>

      <div className="card">
        <div className="upload-row-4">
          <div className="upload-item">
            <h4>1. Нарушения на перроне</h4>
            <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите"
              onFile={(f) => { setPerronFile(f); invalidate(); }} />
            {perronFile && <div className="status-msg">{perronFile.name}</div>}
          </div>
          <div className="upload-item">
            <h4>2. Нарушения в АВК</h4>
            <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите"
              onFile={(f) => { setAvkFile(f); invalidate(); }} />
            {avkFile && <div className="status-msg">{avkFile.name}</div>}
          </div>
          <div className="upload-item">
            <h4>3. Обращения</h4>
            <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите"
              onFile={(f) => { setAppealsFile(f); invalidate(); }} />
            {appealsFile && <div className="status-msg">{appealsFile.name}</div>}
          </div>
          <div className="upload-item">
            <h4>4. Производственные показатели</h4>
            <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите"
              onFile={(f) => { setProductionFile(f); invalidate(); }} />
            {productionFile && <div className="status-msg">{productionFile.name}</div>}
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Период</h3>
        <div className="period-row">
          <label>
            С
            <input type="date" value={startDate}
              onChange={(e) => { setStartDate(e.target.value); invalidate(); }} />
          </label>
          <label>
            По
            <input type="date" value={endDate}
              onChange={(e) => { setEndDate(e.target.value); invalidate(); }} />
          </label>
        </div>
      </div>

      <div className="card">
        <div>
          <button className="btn" onClick={handleBuild} disabled={!startDate || !endDate || loading}>
            Сформировать
          </button>
          {loading && <div className="status-msg">Обработка файлов…</div>}
          {error && <div className="status-msg error">{error}</div>}
        </div>

        {tables.length > 0 && (
          <div style={{ marginTop: 24 }}>
            {tables.map((table) => (
              <SummaryTable key={table.id} table={table} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

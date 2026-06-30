import { useState } from "react";
import FileUpload from "../components/FileUpload";
import SummaryTable from "../components/SummaryTable";
import { Granularity, SummaryTable as SummaryTableData, fetchQualitySummary, fetchMonthSummary } from "../api/qualityReport";

const GRANULARITIES: { id: Granularity; label: string }[] = [
  { id: "week", label: "Неделя" },
  { id: "month", label: "Месяц" },
  { id: "quarter", label: "Квартал" },
  { id: "year", label: "Год" },
];

export default function QualityReportPage() {
  const [granularity, setGranularity] = useState<Granularity>("week");

  const [perronFile, setPerronFile] = useState<File | null>(null);
  const [avkFile, setAvkFile] = useState<File | null>(null);
  const [pabFile, setPabFile] = useState<File | null>(null);
  const [grhFile, setGrhFile] = useState<File | null>(null);
  const [lirFile, setLirFile] = useState<File | null>(null);
  const [appealsFile, setAppealsFile] = useState<File | null>(null);
  const [productionFile, setProductionFile] = useState<File | null>(null);

  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const [tablesByGranularity, setTablesByGranularity] = useState<
    Partial<Record<Granularity, SummaryTableData[]>>
  >({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tables = tablesByGranularity[granularity] ?? [];

  const invalidateCache = () => setTablesByGranularity({});

  const isAggregated = granularity === "month" || granularity === "quarter" || granularity === "year";

  const handleBuild = async () => {
    if (!startDate || !endDate) return;
    setLoading(true);
    setError(null);
    try {
      let result;
      if (isAggregated) {
        result = await fetchMonthSummary(
          { perron: perronFile, avk: avkFile, appeals: appealsFile, production: productionFile },
          startDate,
          endDate,
          granularity
        );
      } else {
        result = await fetchQualitySummary(
          { perron: perronFile, avk: avkFile, grh: grhFile, lir: lirFile, pab: pabFile },
          startDate,
          endDate,
          granularity
        );
      }
      setTablesByGranularity((prev) => ({ ...prev, [granularity]: result.tables }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1>Отчёт по качеству</h1>

      <div className="card">
        <div className="station-switch">
          {GRANULARITIES.map((g) => (
            <button
              key={g.id}
              className={granularity === g.id ? "btn active" : "btn"}
              onClick={() => setGranularity(g.id)}
            >
              {g.label}
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        {isAggregated ? (
          <div className="upload-row-4">
            <div className="upload-item">
              <h4>1. Нарушения на перроне</h4>
              <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите"
                onFile={(f) => { setPerronFile(f); invalidateCache(); }} />
              {perronFile && <div className="status-msg">{perronFile.name}</div>}
            </div>
            <div className="upload-item">
              <h4>2. Нарушения в АВК</h4>
              <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите"
                onFile={(f) => { setAvkFile(f); invalidateCache(); }} />
              {avkFile && <div className="status-msg">{avkFile.name}</div>}
            </div>
            <div className="upload-item">
              <h4>3. Обращения</h4>
              <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите"
                onFile={(f) => { setAppealsFile(f); invalidateCache(); }} />
              {appealsFile && <div className="status-msg">{appealsFile.name}</div>}
            </div>
            <div className="upload-item">
              <h4>4. Производственные показатели</h4>
              <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите"
                onFile={(f) => { setProductionFile(f); invalidateCache(); }} />
              {productionFile && <div className="status-msg">{productionFile.name}</div>}
            </div>
          </div>
        ) : (
          <div className="upload-grid">
            <div className="upload-item">
              <h4>1. Нарушения на перроне</h4>
              <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите"
                onFile={(f) => { setPerronFile(f); invalidateCache(); }} />
              {perronFile && <div className="status-msg">{perronFile.name}</div>}
            </div>
            <div className="upload-item">
              <h4>2. Нарушения в АВК</h4>
              <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите"
                onFile={(f) => { setAvkFile(f); invalidateCache(); }} />
              {avkFile && <div className="status-msg">{avkFile.name}</div>}
            </div>
            <div className="upload-item">
              <h4>3. Проверки PAB</h4>
              <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите"
                onFile={(f) => { setPabFile(f); invalidateCache(); }} />
              {pabFile && <div className="status-msg">{pabFile.name}</div>}
            </div>
            <div className="upload-item">
              <h4>4. Проверки GRH</h4>
              <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите"
                onFile={(f) => { setGrhFile(f); invalidateCache(); }} />
              {grhFile && <div className="status-msg">{grhFile.name}</div>}
            </div>
            <div className="upload-item">
              <h4>5. Мониторинг LIR/СЗВ</h4>
              <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите"
                onFile={(f) => { setLirFile(f); invalidateCache(); }} />
              {lirFile && <div className="status-msg">{lirFile.name}</div>}
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <h3>Период</h3>
        <div className="period-row">
          <label>
            С
            <input
              type="date"
              value={startDate}
              onChange={(e) => {
                setStartDate(e.target.value);
                invalidateCache();
              }}
            />
          </label>
          <label>
            По
            <input
              type="date"
              value={endDate}
              onChange={(e) => {
                setEndDate(e.target.value);
                invalidateCache();
              }}
            />
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

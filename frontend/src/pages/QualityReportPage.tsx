import { useState } from "react";
import FileUpload from "../components/FileUpload";
import SummaryTable from "../components/SummaryTable";
import { Granularity, SummaryTable as SummaryTableData, fetchViolationsSummary } from "../api/qualityReport";

type Section = "violations" | "checks" | "monitoring";

const SECTIONS: { id: Section; label: string }[] = [
  { id: "violations", label: "Нарушения" },
  { id: "checks", label: "Проверки" },
  { id: "monitoring", label: "Мониторинг LIR/СЗВ" },
];

const GRANULARITIES: { id: Granularity; label: string }[] = [
  { id: "week", label: "Неделя" },
  { id: "month", label: "Месяц" },
  { id: "quarter", label: "Квартал" },
  { id: "year", label: "Год" },
];

export default function QualityReportPage() {
  const [section, setSection] = useState<Section>("violations");
  const [granularity, setGranularity] = useState<Granularity>("week");

  const [perronFile, setPerronFile] = useState<File | null>(null);
  const [avkFile, setAvkFile] = useState<File | null>(null);
  const [pabFile, setPabFile] = useState<File | null>(null);
  const [grhFile, setGrhFile] = useState<File | null>(null);
  const [lirFile, setLirFile] = useState<File | null>(null);

  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const [violationsTablesByGranularity, setViolationsTablesByGranularity] = useState<
    Partial<Record<Granularity, SummaryTableData[]>>
  >({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const violationsTables = violationsTablesByGranularity[granularity] ?? [];

  const changeGranularity = (next: Granularity) => {
    setGranularity(next);
  };

  const invalidateViolationsCache = () => setViolationsTablesByGranularity({});

  const handleBuildViolations = async () => {
    if (!perronFile || !avkFile || !startDate || !endDate) return;
    setLoading(true);
    setError(null);
    try {
      const result = await fetchViolationsSummary(perronFile, avkFile, startDate, endDate, granularity);
      setViolationsTablesByGranularity((prev) => ({ ...prev, [granularity]: result.tables }));
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
        <div className="upload-grid">
          <div className="upload-item">
            <h4>1. Нарушения на перроне</h4>
            <FileUpload
              compact
              accept=".xlsx,.xls"
              label="Перетащите файл или нажмите"
              onFile={(f) => {
                setPerronFile(f);
                invalidateViolationsCache();
              }}
            />
            {perronFile && <div className="status-msg">{perronFile.name}</div>}
          </div>
          <div className="upload-item">
            <h4>2. Нарушения в АВК</h4>
            <FileUpload
              compact
              accept=".xlsx,.xls"
              label="Перетащите файл или нажмите"
              onFile={(f) => {
                setAvkFile(f);
                invalidateViolationsCache();
              }}
            />
            {avkFile && <div className="status-msg">{avkFile.name}</div>}
          </div>
          <div className="upload-item">
            <h4>3. Проверки PAB</h4>
            <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите" onFile={setPabFile} />
            {pabFile && <div className="status-msg">{pabFile.name}</div>}
          </div>
          <div className="upload-item">
            <h4>4. Проверки GRH</h4>
            <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите" onFile={setGrhFile} />
            {grhFile && <div className="status-msg">{grhFile.name}</div>}
          </div>
          <div className="upload-item">
            <h4>5. Мониторинг LIR/СЗВ</h4>
            <FileUpload compact accept=".xlsx,.xls" label="Перетащите файл или нажмите" onFile={setLirFile} />
            {lirFile && <div className="status-msg">{lirFile.name}</div>}
          </div>
        </div>
      </div>

      <div className="card">
        <h3>6. Период</h3>
        <div className="period-row">
          <label>
            С
            <input
              type="date"
              value={startDate}
              onChange={(e) => {
                setStartDate(e.target.value);
                invalidateViolationsCache();
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
                invalidateViolationsCache();
              }}
            />
          </label>
        </div>
      </div>

      <div className="card">
        <div className="station-switch">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              className={section === s.id ? "btn active" : "btn"}
              onClick={() => setSection(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {section === "violations" && (
        <div className="card">
          <h3>Нарушения</h3>
          <div className="station-switch">
            {GRANULARITIES.map((g) => (
              <button
                key={g.id}
                className={granularity === g.id ? "btn active" : "btn"}
                onClick={() => changeGranularity(g.id)}
              >
                {g.label}
              </button>
            ))}
          </div>

          <div style={{ marginTop: 16 }}>
            <button
              className="btn"
              onClick={handleBuildViolations}
              disabled={!perronFile || !avkFile || !startDate || !endDate || loading}
            >
              Сформировать
            </button>
            {loading && <div className="status-msg">Обработка файлов…</div>}
            {error && <div className="status-msg error">{error}</div>}
          </div>

          {violationsTables.length > 0 && (
            <div style={{ marginTop: 24 }}>
              {violationsTables.map((table) => (
                <SummaryTable key={table.id} table={table} />
              ))}
            </div>
          )}
        </div>
      )}

      {section === "checks" && (
        <div className="card">
          <h3>Проверки</h3>
          <div className="status-msg">Раздел «Проверки» в разработке.</div>
        </div>
      )}

      {section === "monitoring" && (
        <div className="card">
          <h3>Мониторинг LIR/СЗВ</h3>
          <div className="status-msg">Раздел «Мониторинг LIR/СЗВ» в разработке.</div>
        </div>
      )}
    </div>
  );
}

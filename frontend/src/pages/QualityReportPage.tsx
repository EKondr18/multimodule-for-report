import { useState } from "react";
import FileUpload from "../components/FileUpload";

type Section = "violations" | "checks";
type ViolationsPeriod = "week" | "month" | "quarter" | "year";

const SECTIONS: { id: Section; label: string }[] = [
  { id: "violations", label: "Нарушения" },
  { id: "checks", label: "Проверки" },
];

const VIOLATIONS_PERIODS: { id: ViolationsPeriod; label: string }[] = [
  { id: "week", label: "Неделя" },
  { id: "month", label: "Месяц" },
  { id: "quarter", label: "Квартал" },
  { id: "year", label: "Год" },
];

export default function QualityReportPage() {
  const [section, setSection] = useState<Section>("violations");
  const [violationsPeriod, setViolationsPeriod] = useState<ViolationsPeriod>("week");
  const [file, setFile] = useState<File | null>(null);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  return (
    <div>
      <h1>Отчёт по качеству</h1>

      <div className="card">
        <h3>1. Загрузить эксель-файл</h3>
        <FileUpload accept=".xlsx,.xls" label="Перетащите xlsx-файл сюда или нажмите, чтобы выбрать" onFile={setFile} />
        {file && <div className="status-msg">Выбран файл: {file.name}</div>}
      </div>

      <div className="card">
        <h3>2. Период</h3>
        <div className="period-row">
          <label>
            С
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
          <label>
            По
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
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
            {VIOLATIONS_PERIODS.map((p) => (
              <button
                key={p.id}
                className={violationsPeriod === p.id ? "btn active" : "btn"}
                onClick={() => setViolationsPeriod(p.id)}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="status-msg" style={{ marginTop: 16 }}>
            Логика расчёта раздела «Нарушения» в разработке.
          </div>
        </div>
      )}

      {section === "checks" && (
        <div className="card">
          <h3>Проверки</h3>
          <div className="status-msg">Раздел «Проверки» в разработке.</div>
        </div>
      )}
    </div>
  );
}

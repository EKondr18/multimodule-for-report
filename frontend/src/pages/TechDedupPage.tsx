import { useState } from "react";
import FileUpload from "../components/FileUpload";
import { downloadBlob, removeDuplicates } from "../lib/techDedup";

export default function TechDedupPage() {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (file: File) => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const result = await removeDuplicates(file);
      downloadBlob(result.blob, result.filename);
      setMessage(
        `Было строк: ${result.initialRows}. Осталось: ${result.finalRows}. ` +
          `Удалено дублей: ${result.removedRows}. Файл скачан.`
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1>Удаление дубликатов по обслуживанию техники</h1>

      <div className="card">
        <h3>1. Загрузить выгрузку по обслуживанию техники (xlsx)</h3>
        <FileUpload onFile={handleFile} disabled={loading} />
        {loading && <div className="status-msg">Обработка файла…</div>}
        {message && <div className="status-msg">{message}</div>}
        {error && <div className="status-msg error">{error}</div>}
      </div>
    </div>
  );
}

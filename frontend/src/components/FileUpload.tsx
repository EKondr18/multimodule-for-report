import { useRef, useState } from "react";

interface Props {
  onFile: (file: File) => void;
  disabled?: boolean;
}

export default function FileUpload({ onFile, disabled }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = (files: FileList | null) => {
    const file = files?.[0];
    if (file) onFile(file);
  };

  return (
    <div
      className={`dropzone${dragOver ? " dragover" : ""}`}
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        if (!disabled) handleFiles(e.dataTransfer.files);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx,.xls"
        hidden
        disabled={disabled}
        onChange={(e) => handleFiles(e.target.files)}
      />
      Перетащите xlsx-файл за неделю сюда или нажмите, чтобы выбрать
    </div>
  );
}

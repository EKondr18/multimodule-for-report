import { beforeEach, describe, expect, it, vi } from "vitest";
import * as XLSX from "xlsx";
import { exportRowsToXlsx, sanitizeFilename } from "./exportTableToXlsx";

// XLSX.writeFile в браузере запускает скачивание (нужен document/URL.createObjectURL),
// поэтому подменяем только его: перехватываем книгу и имя файла. Всё остальное в SheetJS —
// настоящее, а проверки идут по байтам, которые реально собираются из книги.
const writeFileMock = vi.hoisted(() => vi.fn());

vi.mock("xlsx", async (importOriginal) => {
  const actual = await importOriginal<typeof import("xlsx")>();
  return { ...actual, writeFile: writeFileMock };
});

type Cell = string | number | null | undefined;

async function exportAndCapture(
  headers: string[],
  rows: Cell[][],
  sheetName?: string
): Promise<{ wb: XLSX.WorkBook; filename: string; reread: Cell[][]; sheetNames: string[] }> {
  if (sheetName === undefined) {
    await exportRowsToXlsx("out.xlsx", headers, rows as (string | number)[][]);
  } else {
    await exportRowsToXlsx("out.xlsx", headers, rows as (string | number)[][], sheetName);
  }
  const [wb, filename] = writeFileMock.mock.calls[0] as [XLSX.WorkBook, string];
  // Настоящая проверка структуры: сериализуем в xlsx-байты и читаем обратно.
  const bytes = new Uint8Array(XLSX.write(wb, { type: "array", bookType: "xlsx" }) as ArrayBuffer);
  const back = XLSX.read(bytes, { type: "array" });
  const reread = XLSX.utils.sheet_to_json<Cell[]>(back.Sheets[back.SheetNames[0]], {
    header: 1,
    defval: null,
    raw: true,
  });
  return { wb, filename, reread, sheetNames: back.SheetNames };
}

beforeEach(() => {
  writeFileMock.mockReset();
});

describe("exportRowsToXlsx: структура файла", () => {
  it("передаёт имя файла в writeFile без изменений", async () => {
    await exportRowsToXlsx("Отчёт.xlsx", ["A"], [[1]]);

    expect(writeFileMock).toHaveBeenCalledTimes(1);
    expect(writeFileMock.mock.calls[0][1]).toBe("Отчёт.xlsx");
  });

  it("по умолчанию создаёт лист «Данные»", async () => {
    const { sheetNames } = await exportAndCapture(["A"], [[1]]);

    expect(sheetNames).toEqual(["Данные"]);
  });

  it("принимает пользовательское имя листа", async () => {
    const { sheetNames } = await exportAndCapture(["A"], [[1]], "Сводка");

    expect(sheetNames).toEqual(["Сводка"]);
  });

  it("первая строка листа — заголовки, далее строки данных в том же порядке", async () => {
    const { reread } = await exportAndCapture(
      ["Модель", "Пробег", "Цена"],
      [
        ["Камаз", 1200, 3500.5],
        ["Газель", 800, 2100],
      ]
    );

    expect(reread).toEqual([
      ["Модель", "Пробег", "Цена"],
      ["Камаз", 1200, 3500.5],
      ["Газель", 800, 2100],
    ]);
  });

  it("результат — валидный xlsx (zip-контейнер с сигнатурой PK)", async () => {
    await exportRowsToXlsx("out.xlsx", ["A"], [[1]]);
    const [wb] = writeFileMock.mock.calls[0] as [XLSX.WorkBook];

    const bytes = new Uint8Array(XLSX.write(wb, { type: "array", bookType: "xlsx" }) as ArrayBuffer);

    expect(String.fromCharCode(bytes[0], bytes[1])).toBe("PK");
  });
});

describe("exportRowsToXlsx: пустые данные", () => {
  it("не бросает исключение при нуле строк и пишет только заголовки", async () => {
    await expect(exportRowsToXlsx("empty.xlsx", ["Модель", "Пробег"], [])).resolves.toBeUndefined();

    const [wb] = writeFileMock.mock.calls[0] as [XLSX.WorkBook];
    const reread = XLSX.utils.sheet_to_json<Cell[]>(wb.Sheets["Данные"], {
      header: 1,
      defval: null,
    });
    expect(reread).toEqual([["Модель", "Пробег"]]);
  });
});

describe("exportRowsToXlsx: значения ячеек", () => {
  it("null и undefined превращаются в пустую строку, а не в текст 'null'", async () => {
    const { wb } = await exportAndCapture(["A", "B"], [[null, undefined]]);

    expect(wb.Sheets["Данные"]["A2"].v).toBe("");
    expect(wb.Sheets["Данные"]["B2"].v).toBe("");
  });

  it("число 0 сохраняется как число 0, а не заменяется пустой строкой", async () => {
    const { wb } = await exportAndCapture(["A"], [[0]]);

    expect(wb.Sheets["Данные"]["A2"].v).toBe(0);
    expect(wb.Sheets["Данные"]["A2"].t).toBe("n");
  });

  it("числа остаются числами после сохранения", async () => {
    const { reread } = await exportAndCapture(["Сумма"], [[1234.5]]);

    expect(reread[1][0]).toBe(1234.5);
  });

  it("пустая строка остаётся пустой", async () => {
    const { wb } = await exportAndCapture(["A"], [[""]]);

    expect(wb.Sheets["Данные"]["A2"].v).toBe("");
  });
});

describe("exportRowsToXlsx: кириллица", () => {
  it("заголовки и значения с кириллицей, «ё», кавычками и дефисами переживают round-trip", async () => {
    const headers = ["Заказ-наряд", "Контрагент", "Комментарий"];
    const rows: Cell[][] = [
      ["Заказ-наряд №001 от 05.12.2024 / Закрыт", "ООО «Ёлочка»", "Замена масла — выполнена"],
      ["Заказ-наряд №002 / В работе", "ИП Йылдыз", "Тёплый прием"],
    ];

    const { reread } = await exportAndCapture(headers, rows);

    expect(reread).toEqual([headers, ...rows]);
  });

  it("имя листа с кириллицей сохраняется", async () => {
    const { sheetNames } = await exportAndCapture(["A"], [[1]], "Итоги за квартал");

    expect(sheetNames).toEqual(["Итоги за квартал"]);
  });
});

describe("sanitizeFilename", () => {
  it("заменяет символы, недопустимые в именах файлов, на подчёркивание", () => {
    expect(sanitizeFilename('Отчёт: "Q1"/2024?*<>|\\')).toBe("Отчёт_ _Q1_2024_");
  });

  it("убирает пробелы по краям", () => {
    expect(sanitizeFilename("   Сводка   ")).toBe("Сводка");
  });

  it("для пустого или пробельного названия возвращает 'table'", () => {
    expect(sanitizeFilename("")).toBe("table");
    expect(sanitizeFilename("   ")).toBe("table");
  });

  it("сохраняет кириллицу и обычные пробелы внутри названия", () => {
    expect(sanitizeFilename("Удаление дубликатов по технике")).toBe("Удаление дубликатов по технике");
  });
});

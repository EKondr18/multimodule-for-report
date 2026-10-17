import { describe, expect, it } from "vitest";
import * as XLSX from "xlsx";
import { removeDuplicates } from "./techDedup";

// Схема выгрузки: «Заказ-наряд» — основное поле, по которому идёт дедупликация.
// «Контрагенты», «Цена», «Сумма» и «Автомобиль.Модель автомобиля» исключены
// из финального сравнения на точные дубли (см. techDedup.ts).
const HEADER = [
  "Заказ-наряд",
  "Контрагенты",
  "Цена",
  "Сумма",
  "Автомобиль.Модель автомобиля",
  "Пробег",
];

type Cell = string | number | null;

/**
 * jsdom не реализует Blob/File.prototype.arrayBuffer, а removeDuplicates
 * читает входной файл именно через него. Добавляем метод поверх FileReader,
 * который jsdom поддерживает — код модуля при этом не меняется.
 */
function readAsArrayBuffer(blob: Blob): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}

function withArrayBuffer(blob: Blob): Blob {
  Object.defineProperty(blob, "arrayBuffer", {
    value: () => readAsArrayBuffer(blob),
    configurable: true,
  });
  return blob;
}

function workbookToBytes(wb: XLSX.WorkBook): ArrayBuffer {
  return XLSX.write(wb, { type: "array", bookType: "xlsx" }) as ArrayBuffer;
}

/** Входной файл из набора листов: { имя листа: массив строк (первая — заголовок) }. */
function makeInputFile(sheets: Record<string, Cell[][]>, name = "input.xlsx"): File {
  const wb = XLSX.utils.book_new();
  for (const [sheetName, aoa] of Object.entries(sheets)) {
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(aoa), sheetName);
  }
  const file = new File([workbookToBytes(wb)], name);
  return withArrayBuffer(file) as File;
}

/** Читает результат обратно: лист и его строки (включая заголовок). */
async function readResultRows(blob: Blob): Promise<{ sheetNames: string[]; rows: Cell[][]; wb: XLSX.WorkBook }> {
  const bytes = new Uint8Array(await readAsArrayBuffer(blob));
  const wb = XLSX.read(bytes, { type: "array", cellNF: true });
  const sheetName = wb.SheetNames[0];
  const rows = XLSX.utils.sheet_to_json<Cell[]>(wb.Sheets[sheetName], {
    header: 1,
    defval: null,
    raw: true,
  });
  return { sheetNames: wb.SheetNames, rows, wb };
}

/** Строки данных без заголовка, только значения столбца «Заказ-наряд» и «Пробег». */
function dataKeys(rows: Cell[][]): { order: Cell; mileage: Cell }[] {
  return rows.slice(1).map((r) => ({ order: r[0], mileage: r[5] }));
}

describe("removeDuplicates: без дублей", () => {
  it("не меняет набор строк, если номера заказов уникальны", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 от 05.12.2024 / Закрыт", "ООО «Ромашка»", 100, 100, "Камаз", 1000],
        ["Заказ-наряд №002 от 05.12.2024 / Открыт", "ООО «Лилия»", 200, 200, "Газель", 2000],
      ],
    });

    const result = await removeDuplicates(file);

    expect(result.initialRows).toBe(2);
    expect(result.finalRows).toBe(2);
    expect(result.removedRows).toBe(0);
  });

  it("сохраняет кириллицу в тексте заказов и контрагентов", async () => {
    const order = "Заказ-наряд №001 от 05.12.2024 / Закрыт";
    const file = makeInputFile({
      Данные: [HEADER, [order, "ООО «Ромашка»", 100, 100, "Камаз", 1000]],
    });

    const result = await removeDuplicates(file);
    const { rows } = await readResultRows(result.blob);

    expect(rows[1][0]).toBe(order);
    expect(rows[1][1]).toBe("ООО «Ромашка»");
  });

  it("обрабатывает файл только с заголовком (0 строк данных) без исключения", async () => {
    const file = makeInputFile({ Данные: [HEADER] });

    const result = await removeDuplicates(file);
    const { rows } = await readResultRows(result.blob);

    expect(result.initialRows).toBe(0);
    expect(result.finalRows).toBe(0);
    expect(rows).toEqual([HEADER]);
  });
});

describe("removeDuplicates: шаг 1 — самая свежая дата по номеру заказа", () => {
  it("для одного номера оставляет только строку с самой свежей датой", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 от 05.12.2024 / Закрыт", "ООО «А»", 1, 1, "Камаз", 100],
        ["Заказ-наряд №001 от 10.12.2024 / Открыт", "ООО «А»", 1, 1, "Камаз", 120],
      ],
    });

    const result = await removeDuplicates(file);
    const { rows } = await readResultRows(result.blob);

    expect(result.removedRows).toBe(1);
    expect(dataKeys(rows)).toEqual([{ order: "Заказ-наряд №001 от 10.12.2024 / Открыт", mileage: 120 }]);
  });

  it("сравнивает даты по календарю (год-месяц-день), а не как строки", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 от 31.12.2024 / Закрыт", "ООО «А»", 1, 1, "Камаз", 1],
        ["Заказ-наряд №001 от 01.01.2025 / Открыт", "ООО «А»", 1, 1, "Камаз", 2],
      ],
    });

    const result = await removeDuplicates(file);
    const { rows } = await readResultRows(result.blob);

    expect(dataKeys(rows).map((r) => r.mileage)).toEqual([2]);
  });

  it("разные номера заказов не влияют друг на друга", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 от 05.12.2024 / Закрыт", "ООО «А»", 1, 1, "Камаз", 1],
        ["Заказ-наряд №002 от 01.01.2025 / Закрыт", "ООО «А»", 1, 1, "Камаз", 2],
      ],
    });

    const result = await removeDuplicates(file);

    expect(result.finalRows).toBe(2);
  });

  it("FLAG (for human review): строка без распознанной даты в группе с датой отбрасывается", async () => {
    // FLAG (for human review): docstring Python-версии говорит, что группа с «неполной»
    // датой остаётся целиком; но если в группе есть и полная дата, и неполная
    // («от 26.02» без года), строка с неполной датой отбрасывается, т.к. null !== maxDate.
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 от 26.02 / Открыт", "ООО «А»", 1, 1, "Камаз", 1],
        ["Заказ-наряд №001 от 26.02.2025 / Закрыт", "ООО «А»", 1, 1, "Камаз", 2],
      ],
    });

    const result = await removeDuplicates(file);
    const { rows } = await readResultRows(result.blob);

    expect(dataKeys(rows).map((r) => r.mileage)).toEqual([2]);
    expect(result.removedRows).toBe(1);
  });

  it("группа без единой даты: шаг 1 пропускается, но шаг 2 (приоритет статуса) применяется", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 / Открыт", "ООО «А»", 1, 1, "Камаз", 1],
        ["Заказ-наряд №001 / Закрыт", "ООО «А»", 1, 1, "Камаз", 2],
      ],
    });

    const result = await removeDuplicates(file);
    const { rows } = await readResultRows(result.blob);

    expect(dataKeys(rows).map((r) => r.mileage)).toEqual([2]);
  });

  it("группа без единой даты с одинаковым статусом остаётся целиком", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 / Открыт", "ООО «А»", 1, 1, "Камаз", 1],
        ["Заказ-наряд №001 / Открыт", "ООО «А»", 1, 1, "Камаз", 2],
      ],
    });

    const result = await removeDuplicates(file);

    expect(result.finalRows).toBe(2);
  });
});

describe("removeDuplicates: шаг 2 — приоритет статуса при совпадении даты", () => {
  it("при одинаковой свежей дате «Закрыт» побеждает «В работе»", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 от 05.12.2024 / В работе", "ООО «А»", 1, 1, "Камаз", 1],
        ["Заказ-наряд №001 от 05.12.2024 / Закрыт", "ООО «А»", 1, 1, "Камаз", 2],
      ],
    });

    const result = await removeDuplicates(file);
    const { rows } = await readResultRows(result.blob);

    expect(dataKeys(rows).map((r) => r.mileage)).toEqual([2]);
  });

  it("порядок статусов: Закрыт > Выполнен > В работе > Открыт", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 от 05.12.2024 / Открыт", "ООО «А»", 1, 1, "Камаз", 4],
        ["Заказ-наряд №001 от 05.12.2024 / В работе", "ООО «А»", 1, 1, "Камаз", 3],
        ["Заказ-наряд №001 от 05.12.2024 / Выполнен", "ООО «А»", 1, 1, "Камаз", 2],
        ["Заказ-наряд №001 от 05.12.2024 / Закрыт", "ООО «А»", 1, 1, "Камаз", 1],
      ],
    });

    const result = await removeDuplicates(file);
    const { rows } = await readResultRows(result.blob);

    expect(dataKeys(rows).map((r) => r.mileage)).toEqual([1]);
  });

  it("приоритет статуса учитывается только внутри самой свежей даты", async () => {
    // Старая дата с «Закрыт» проигрывает новой дате с «Открыт»: сначала отбирается дата.
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 от 01.01.2024 / Закрыт", "ООО «А»", 1, 1, "Камаз", 1],
        ["Заказ-наряд №001 от 05.12.2024 / Открыт", "ООО «А»", 1, 1, "Камаз", 2],
      ],
    });

    const result = await removeDuplicates(file);
    const { rows } = await readResultRows(result.blob);

    expect(dataKeys(rows).map((r) => r.mileage)).toEqual([2]);
  });

  it("статус регистронезависим", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 от 05.12.2024 / В РАБОТЕ", "ООО «А»", 1, 1, "Камаз", 1],
        ["Заказ-наряд №001 от 05.12.2024 / ЗАКРЫТ", "ООО «А»", 1, 1, "Камаз", 2],
      ],
    });

    const result = await removeDuplicates(file);
    const { rows } = await readResultRows(result.blob);

    expect(dataKeys(rows).map((r) => r.mileage)).toEqual([2]);
  });

  it("неизвестный статус получает приоритет 99 и проигрывает известному", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 от 05.12.2024 / Отменён", "ООО «А»", 1, 1, "Камаз", 1],
        ["Заказ-наряд №001 от 05.12.2024 / Открыт", "ООО «А»", 1, 1, "Камаз", 2],
      ],
    });

    const result = await removeDuplicates(file);
    const { rows } = await readResultRows(result.blob);

    expect(dataKeys(rows).map((r) => r.mileage)).toEqual([2]);
  });
});

describe("removeDuplicates: шаг 3 — точные дубли после фильтрации", () => {
  it("строки, отличающиеся только в исключённых столбцах (Цена/Сумма/Контрагенты), схлопываются до одной", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 от 05.12.2024 / Закрыт", "ООО «А»", 100, 100, "Камаз", 500],
        ["Заказ-наряд №001 от 05.12.2024 / Закрыт", "ООО «Б»", 100.4, 99.6, "Камаз", 500],
      ],
    });

    const result = await removeDuplicates(file);

    expect(result.finalRows).toBe(1);
  });

  it("при схлопывании дубликатов остаётся последнее вхождение (keep='last')", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 от 05.12.2024 / Закрыт", "ООО «А»", 100, 100, "Камаз", 500],
        ["Заказ-наряд №001 от 05.12.2024 / Закрыт", "ООО «Б»", 101, 101, "Камаз", 500],
      ],
    });

    const result = await removeDuplicates(file);
    const { rows } = await readResultRows(result.blob);

    expect(rows.length - 1).toBe(1);
    expect(rows[1][1]).toBe("ООО «Б»");
    expect(rows[1][2]).toBe(101);
  });

  it("строки, отличающиеся в обычном столбце (Пробег), остаются обе", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 от 05.12.2024 / Закрыт", "ООО «А»", 100, 100, "Камаз", 500],
        ["Заказ-наряд №001 от 05.12.2024 / Закрыт", "ООО «А»", 100, 100, "Камаз", 501],
      ],
    });

    const result = await removeDuplicates(file);

    expect(result.finalRows).toBe(2);
  });

  it("строки без номера заказа не объединяются шагами 1-2, но участвуют в точной дедупликации", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        [null, "ООО «А»", 1, 1, "Камаз", 7],
        [null, "ООО «А»", 1, 1, "Камаз", 7],
        ["Заказ-наряд №001 от 05.12.2024 / Закрыт", "ООО «А»", 1, 1, "Камаз", 8],
      ],
    });

    const result = await removeDuplicates(file);
    const { rows } = await readResultRows(result.blob);

    // два одинаковых пустых заказа схлопнулись в одну строку, заказ №001 сохранён
    expect(result.finalRows).toBe(2);
    expect(dataKeys(rows).map((r) => r.mileage)).toEqual([7, 8]);
  });

  // FLAG (for human review): столбец «Заказ-наряд» исключён из ключа точной дедупликации
  // (шаг 3), поэтому два РАЗНЫХ заказа с одинаковыми остальными полями схлопываются в одну строку.
  it("FLAG (for human review): разные заказы-наряды с одинаковыми прочими полями схлопываются в одну строку", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №001 от 05.12.2024 / Закрыт", "ООО «А»", 1, 1, "Камаз", 500],
        ["Заказ-наряд №002 от 05.12.2024 / Закрыт", "ООО «А»", 1, 1, "Камаз", 500],
      ],
    });

    const result = await removeDuplicates(file);
    const { rows } = await readResultRows(result.blob);

    expect(result.finalRows).toBe(1);
    expect(rows[1][0]).toBe("Заказ-наряд №002 от 05.12.2024 / Закрыт");
  });

  // FLAG (for human review): без «№» ключ заказа — это текст до «/», который включает дату
  // («000123 от 01.01.2024»). Поэтому записи с одним номером и разными датами не группируются
  // на шаге 1, и «самая свежая дата» не работает. Ниже — текущее поведение.
  it("FLAG (for human review): без «№» ключ заказа включает дату, и записи с разными датами не группируются", async () => {
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["000123 от 01.01.2024 / Открыт", "ООО «А»", 1, 1, "Камаз", 1],
        ["000123 от 02.01.2024 / Открыт", "ООО «А»", 1, 1, "Камаз", 2],
      ],
    });

    const result = await removeDuplicates(file);

    expect(result.finalRows).toBe(2);
  });
});

describe("removeDuplicates: выбор листа и структура", () => {
  it("берёт первый лист, где есть столбец «Заказ-наряд», а не первый лист книги", async () => {
    const file = makeInputFile({
      Сводка: [["Итого", 42]],
      Данные: [HEADER, ["Заказ-наряд №001 от 05.12.2024 / Закрыт", "ООО «А»", 1, 1, "Камаз", 1]],
    });

    const result = await removeDuplicates(file);
    const { sheetNames } = await readResultRows(result.blob);

    expect(result.initialRows).toBe(1);
    expect(sheetNames).toEqual(["Данные"]);
  });

  it("бросает понятную ошибку, если нет листа со столбцом «Заказ-наряд»", async () => {
    const file = makeInputFile({ Лист1: [["Другое", "Столбец"], [1, 2]] });

    await expect(removeDuplicates(file)).rejects.toThrow(
      "Не найден лист со столбцом «Заказ-наряд» — проверьте структуру файла"
    );
  });

  it("имя выходного файла: суффикс _cleaned и расширение .xlsx", async () => {
    const file = makeInputFile({ Данные: [HEADER] }, "Выгрузка техники.xls");

    const result = await removeDuplicates(file);

    expect(result.filename).toBe("Выгрузка техники_cleaned.xlsx");
  });

  it("выходной файл — это xlsx (zip-контейнер) с MIME-типом Excel", async () => {
    const file = makeInputFile({ Данные: [HEADER] });

    const result = await removeDuplicates(file);
    const bytes = new Uint8Array(await readAsArrayBuffer(result.blob));

    expect(result.blob.type).toBe("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    // zip-файлы начинаются с сигнатуры "PK"
    expect(String.fromCharCode(bytes[0], bytes[1])).toBe("PK");
  });

  it("возвращает формат даты на место (dd.mm.yyyy не превращается в серийный номер)", async () => {
    // 45566 — серийный номер 01.10.2024 в Excel
    const wb = XLSX.utils.book_new();
    const aoa: Cell[][] = [
      ["Заказ-наряд", "Дата выдачи", "Пробег"],
      ["Заказ-наряд №001 от 05.12.2024 / Закрыт", 45566, 1],
    ];
    const sheet = XLSX.utils.aoa_to_sheet(aoa);
    sheet["B2"].z = "dd.mm.yyyy";
    XLSX.utils.book_append_sheet(wb, sheet, "Данные");
    const file = withArrayBuffer(new File([workbookToBytes(wb)], "in.xlsx")) as File;

    const result = await removeDuplicates(file);
    const { wb: out } = await readResultRows(result.blob);
    const outCell = out.Sheets["Данные"]["B2"];

    expect(outCell.v).toBe(45566);
    expect(outCell.z).toBe("dd.mm.yyyy");
    expect(XLSX.SSF.is_date(outCell.z as string)).toBe(true);
  });
});

describe("removeDuplicates: характеризация расхождений с Python-версией (FLAG)", () => {
  it("кириллический суффикс в номере наряда различает разные заказы (не ASCII-only \\w)", async () => {
    // Регэксп №\s*[\p{L}\p{N}_-]+ с флагом u захватывает кириллицу, так что
    // «№00012А» и «№00012Б» — два разных номера наряда, оба сохраняются.
    const file = makeInputFile({
      Данные: [
        HEADER,
        ["Заказ-наряд №00012А от 01.01.2025 / Открыт", "ООО «А»", 1, 1, "Камаз", 1],
        ["Заказ-наряд №00012Б от 02.01.2025 / Открыт", "ООО «А»", 1, 1, "Камаз", 2],
      ],
    });

    const result = await removeDuplicates(file);
    const { rows } = await readResultRows(result.blob);

    expect(dataKeys(rows).map((r) => r.mileage)).toEqual([1, 2]);
  });
});

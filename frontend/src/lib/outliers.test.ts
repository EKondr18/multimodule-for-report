import { describe, expect, it } from "vitest";
import {
  computeOutlierCells,
  looksLikeIdentifierColumn,
  outlierKey,
  type CellValue,
} from "./outliers";

type Row = Record<string, CellValue>;

/** Строки с одним столбцом "Выручка": девять одинаковых значений и один выброс. */
function rowsWithOneOutlier(base: number, outlier: number): Row[] {
  return [...Array(9)].map(() => ({ Выручка: base })).concat([{ Выручка: outlier }]);
}

describe("computeOutlierCells: основной сценарий", () => {
  it("помечает явный выброс в числовом столбце", () => {
    // mean=19, std=27 -> z(100)=3 > 2, z(10)≈0.33
    const flagged = computeOutlierCells(rowsWithOneOutlier(10, 100), ["Выручка"]);

    expect([...flagged]).toEqual([outlierKey(9, "Выручка")]);
  });

  it("не помечает обычные значения рядом с выбросом", () => {
    const flagged = computeOutlierCells(rowsWithOneOutlier(10, 100), ["Выручка"]);

    for (let i = 0; i < 9; i++) {
      expect(flagged.has(outlierKey(i, "Выручка"))).toBe(false);
    }
  });

  it("возвращает пустой набор для пустого списка строк", () => {
    expect(computeOutlierCells([], ["Выручка"]).size).toBe(0);
  });

  it("анализирует только переданные столбцы", () => {
    const rows: Row[] = rowsWithOneOutlier(10, 100).map((r) => ({ ...r, Прочее: 1 }));

    const flagged = computeOutlierCells(rows, ["Прочее"]);

    expect(flagged.size).toBe(0);
  });
});

describe("computeOutlierCells: нулевой разброс", () => {
  it("не помечает столбец, где все значения одинаковы (std = 0)", () => {
    const rows: Row[] = [...Array(10)].map(() => ({ Выручка: 7 }));

    expect(computeOutlierCells(rows, ["Выручка"]).size).toBe(0);
  });
});

describe("computeOutlierCells: минимальный размер выборки", () => {
  it("не анализирует столбец с числом числовых значений меньше minSamples (по умолчанию 5)", () => {
    // 4 числовых значения, выброс очевиден, но выборка слишком мала
    const rows: Row[] = [{ X: 1 }, { X: 1 }, { X: 1 }, { X: 100 }];

    expect(computeOutlierCells(rows, ["X"]).size).toBe(0);
  });

  it("учитывает minSamples из опций (порог снижен, т.к. при n=4 макс. z ≈ 1.73)", () => {
    const rows: Row[] = [{ X: 1 }, { X: 1 }, { X: 1 }, { X: 100 }];

    const flagged = computeOutlierCells(rows, ["X"], { minSamples: 4, thresholdStdDev: 1.5 });

    expect(flagged.has(outlierKey(3, "X"))).toBe(true);
  });

  // FLAG (for human review): при minSamples=5 и пороге 2.0 столбец из ровно 5 чисел
  // никогда не даст выброс: максимальный z-score одной точки (population std)
  // равен sqrt(n-1) = 2, а сравнение строгое (>). Ниже тест фиксирует текущее поведение.
  it("FLAG (for human review): на выборке из 5 чисел выброс не помечается даже при явном отклонении", () => {
    const rows: Row[] = [{ X: 0 }, { X: 0 }, { X: 0 }, { X: 0 }, { X: 1000 }];

    expect(computeOutlierCells(rows, ["X"]).size).toBe(0);
  });
});

describe("computeOutlierCells: доля числовых значений", () => {
  it("исключает столбец, где числовых значений меньше 60% строк", () => {
    // 5 из 10 числовых (50%) -> столбец не анализируется, хотя выброс есть
    const rows: Row[] = [
      ...[1, 1, 1, 1, 100].map((v) => ({ X: v })),
      ...[...Array(5)].map(() => ({ X: "текст" })),
    ];

    expect(computeOutlierCells(rows, ["X"]).size).toBe(0);
  });

  it("включает столбец ровно при 60% числовых значений (граница включительно)", () => {
    // 6 из 10 числовых (60%) -> анализируется
    const rows: Row[] = [
      ...[1, 1, 1, 1, 1, 100].map((v) => ({ X: v })),
      ...[...Array(4)].map(() => ({ X: "текст" })),
    ];

    const flagged = computeOutlierCells(rows, ["X"]);

    expect(flagged.has(outlierKey(5, "X"))).toBe(true);
  });

  it("пустые ячейки (null, undefined, '') считаются нечисловыми", () => {
    const rows: Row[] = [
      ...[1, 1, 1, 1, 1, 100].map((v) => ({ X: v })),
      { X: null },
      { X: undefined },
      { X: "" },
      { X: "   " },
    ];

    // 6 из 10 -> граница 60%, столбец анализируется
    expect(computeOutlierCells(rows, ["X"]).has(outlierKey(5, "X"))).toBe(true);
  });
});

describe("computeOutlierCells: разбор чисел", () => {
  it("обрабатывает отрицательные числа", () => {
    // nine -10 and one -500 -> z(-500)=3
    const rows: Row[] = [...Array(9)].map(() => ({ T: -10 })).concat([{ T: -500 }]);

    const flagged = computeOutlierCells(rows, ["T"]);

    expect([...flagged]).toEqual([outlierKey(9, "T")]);
  });

  it("разбирает строковые числа с пробелом-разделителем тысяч и запятой-десятичным", () => {
    // "1 000,5" -> 1000.5, остальные "10" -> выброс только у первой строки
    const rows: Row[] = [
      { Сумма: "1 000,5" },
      ...[...Array(9)].map(() => ({ Сумма: "10" })),
    ];

    const flagged = computeOutlierCells(rows, ["Сумма"]);

    expect([...flagged]).toEqual([outlierKey(0, "Сумма")]);
  });

  it("строки с числом в тексте (например '12 шт') не являются числами", () => {
    // 'шт' ломает разбор -> значения считаются нечисловыми, столбец пропускается
    const rows: Row[] = [
      ...[1, 1, 1, 1, 1, 100].map((v) => ({ X: `${v} шт` })),
    ];

    expect(computeOutlierCells(rows, ["X"]).size).toBe(0);
  });

  it("NaN и Infinity не считаются числами", () => {
    const rows: Row[] = [
      ...[1, 1, 1, 1, 1, 100].map((v) => ({ X: v })),
      { X: Number.NaN },
      { X: Number.POSITIVE_INFINITY },
    ];

    // 6 из 10 числовых с учётом того, что NaN и Infinity — нечисловые (6/10 = 60%)
    expect(computeOutlierCells(rows, ["X"]).has(outlierKey(5, "X"))).toBe(true);
  });
});

describe("looksLikeIdentifierColumn: исключение идентификаторов и дат", () => {
  it.each([
    "id",
    "ID клиента",
    "ИД",
    "№ рейса",
    "Заказ №",
    "Номер",
    "код",
    "Код товара",
    "Дата",
    "дата отправления",
    "date",
    "Период",
    "Год",
    "Месяц",
    "Квартал",
    "Неделя",
    "ID_клиента",
    "Код (внутр.)",
  ])("распознаёт идентификатор/дату: %s", (name) => {
    expect(looksLikeIdentifierColumn(name)).toBe(true);
  });

  it.each([
    "Выручка",
    "Сумма, руб.",
    "Номенклатура", // «номер» внутри слова, не отдельное слово
    "Датчик", // «дата» внутри слова
    "Идентификатор", // «ид» внутри слова
    "Кодировка",
    "Количество",
  ])("не считает обычную метрику идентификатором: %s", (name) => {
    expect(looksLikeIdentifierColumn(name)).toBe(false);
  });

  it("исключённый по названию столбец не помечается даже при явном выбросе", () => {
    const rows: Row[] = rowsWithOneOutlier(10, 100).map((r) => ({ ...r, "№ рейса": r.Выручка }));

    const flagged = computeOutlierCells(rows, ["№ рейса"]);

    expect(flagged.size).toBe(0);
  });
});

describe("outlierKey", () => {
  it("формирует ключ вида '<индекс>:<столбец>'", () => {
    expect(outlierKey(3, "Выручка")).toBe("3:Выручка");
  });
});

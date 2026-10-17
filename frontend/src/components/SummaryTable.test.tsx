import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SummaryTable as SummaryTableData } from "../api/qualityReport";
import SummaryTable from "./SummaryTable";

// Выбросы: девять значений 10 и одно 100 -> только 100 (z=3) помечается.
function tableWithOutlier(): SummaryTableData {
  return {
    id: "t1",
    title: "Сводка по качеству",
    columns: ["Модель", "Выручка"],
    rows: [
      ...[...Array(9)].map(() => ({ Модель: "Камаз", Выручка: 10 })),
      { Модель: "Газель", Выручка: 100 },
    ],
  };
}

const OUTLIER_CLASS = "cell-outlier";

describe("SummaryTable: рендер", () => {
  it("показывает заголовок таблицы, заголовки столбцов и строки", () => {
    render(<SummaryTable table={tableWithOutlier()} />);

    expect(screen.getByText("Сводка по качеству")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Модель" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Выручка" })).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(1 + 10);
  });

  it("форматирует числа по ru-RU", () => {
    const table: SummaryTableData = {
      id: "t",
      title: "T",
      columns: ["Сумма"],
      rows: [{ Сумма: 1234567 }],
    };

    render(<SummaryTable table={table} />);

    // Testing Library нормализует пробелы в тексте DOM (NBSP -> пробел), нормализуем и запрос.
    const expected = (1234567).toLocaleString("ru-RU").replace(/\s/g, " ");
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("показывает message вместо таблицы, если он задан", () => {
    const table: SummaryTableData = {
      id: "t",
      title: "Пусто",
      columns: ["A"],
      rows: [],
      message: "Нет данных за выбранный период",
    };

    render(<SummaryTable table={table} />);

    expect(screen.getByText("Нет данных за выбранный период")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Копировать" })).not.toBeInTheDocument();
  });

  it("содержит кнопки «Копировать» и «Экспорт в Excel»", () => {
    render(<SummaryTable table={tableWithOutlier()} />);

    expect(screen.getByRole("button", { name: "Копировать" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Экспорт в Excel" })).toBeEnabled();
  });

  it("кнопка экспорта отключена, если строк нет", () => {
    const table: SummaryTableData = { id: "t", title: "T", columns: ["A"], rows: [] };

    render(<SummaryTable table={table} />);

    expect(screen.getByRole("button", { name: "Экспорт в Excel" })).toBeDisabled();
  });
});

describe("SummaryTable: подсветка выбросов", () => {
  it("помечает выброс классом cell-outlier и подсказкой по умолчанию", () => {
    render(<SummaryTable table={tableWithOutlier()} />);

    const outlierCell = screen.getByText("100");
    expect(outlierCell).toHaveClass(OUTLIER_CLASS);
    expect(outlierCell).toHaveAttribute("title", expect.stringContaining("Статистический выброс"));
  });

  it("обычные значения не помечаются", () => {
    render(<SummaryTable table={tableWithOutlier()} />);

    const normalCells = screen.getAllByText("10");
    for (const cell of normalCells) {
      expect(cell).not.toHaveClass(OUTLIER_CLASS);
    }
  });

  it("при highlightOutliers={false} выбросы не помечаются", () => {
    render(<SummaryTable table={tableWithOutlier()} highlightOutliers={false} />);

    expect(screen.getByText("100")).not.toHaveClass(OUTLIER_CLASS);
  });

  it("столбец-идентификатор не анализируется", () => {
    const table: SummaryTableData = {
      id: "t",
      title: "T",
      columns: ["№ рейса"],
      rows: [...[...Array(9)].map(() => ({ "№ рейса": 10 })), { "№ рейса": 100 }],
    };

    const { container } = render(<SummaryTable table={table} />);

    expect(container.querySelector(`.${OUTLIER_CLASS}`)).toBeNull();
  });
});

describe("SummaryTable: копирование в буфер", () => {
  let writeText: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
  });

  it("копирует таблицу как TSV с заголовками и подтверждает копирование", async () => {
    const table: SummaryTableData = {
      id: "t",
      title: "T",
      columns: ["Модель", "Выручка"],
      rows: [{ Модель: "Камаз", Выручка: 10 }],
    };
    render(<SummaryTable table={table} />);

    fireEvent.click(screen.getByRole("button", { name: "Копировать" }));

    expect(writeText).toHaveBeenCalledWith("Модель\tВыручка\nКамаз\t10");
    expect(await screen.findByRole("button", { name: "✓ Скопировано" })).toBeInTheDocument();
  });
});

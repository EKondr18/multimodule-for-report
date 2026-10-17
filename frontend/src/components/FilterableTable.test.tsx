import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import FilterableTable from "./FilterableTable";

const COLUMNS = [
  { key: "model", label: "Модель" },
  { key: "mileage", label: "Пробег" },
];

// Девять "10" и одно "100": только 100 — выброс.
const OUTLIER_ROWS = [
  ...[...Array(9)].map(() => ({ model: "Камаз", mileage: "10" })),
  { model: "Газель", mileage: "100" },
];

describe("FilterableTable: рендер", () => {
  it("показывает заголовки столбцов и строки данных", () => {
    render(<FilterableTable columns={COLUMNS} rows={OUTLIER_ROWS.slice(9)} />);

    expect(screen.getByRole("columnheader", { name: "Модель" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Пробег" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Газель" })).toBeInTheDocument();
  });

  it("содержит кнопку «Экспорт в Excel»", () => {
    render(<FilterableTable columns={COLUMNS} rows={OUTLIER_ROWS} />);

    expect(screen.getByRole("button", { name: "Экспорт в Excel" })).toBeEnabled();
  });

  it("кнопка экспорта отключена, если строк нет", () => {
    render(<FilterableTable columns={COLUMNS} rows={[]} />);

    expect(screen.getByRole("button", { name: "Экспорт в Excel" })).toBeDisabled();
  });

  it("выводит строку «Итого» с итогами, если переданы totals", () => {
    render(<FilterableTable columns={COLUMNS} rows={OUTLIER_ROWS} totals={{ mileage: "190" }} />);

    const totalsRow = screen.getByText("Итого").closest("tr") as HTMLElement;
    expect(within(totalsRow).getByText("190")).toBeInTheDocument();
  });
});

describe("FilterableTable: пагинация", () => {
  it("делит строки на страницы и показывает счётчик", () => {
    const rows = [...Array(5)].map((_, i) => ({ model: `М${i}`, mileage: String(i) }));

    render(<FilterableTable columns={COLUMNS} rows={rows} pageSize={2} />);

    expect(screen.getByText("Стр. 1 из 3 (5 строк из 5)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Назад" })).toBeDisabled();
  });

  it("переключает страницы кнопками «Вперёд» и «Назад»", () => {
    const rows = [...Array(5)].map((_, i) => ({ model: `М${i}`, mileage: String(i) }));
    render(<FilterableTable columns={COLUMNS} rows={rows} pageSize={2} />);

    fireEvent.click(screen.getByRole("button", { name: "Вперёд" }));
    expect(screen.getByText("Стр. 2 из 3 (5 строк из 5)")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Назад" }));
    expect(screen.getByText("Стр. 1 из 3 (5 строк из 5)")).toBeInTheDocument();
  });
});

describe("FilterableTable: фильтры", () => {
  it("для столбца с ≤30 уникальными значениями показывает выпадающий список", () => {
    render(<FilterableTable columns={COLUMNS} rows={OUTLIER_ROWS} />);

    expect(screen.getAllByRole("combobox")).toHaveLength(2);
    expect(screen.queryByPlaceholderText("Фильтр...")).not.toBeInTheDocument();
  });

  it("выбор значения в фильтре оставляет только подходящие строки", () => {
    render(<FilterableTable columns={COLUMNS} rows={OUTLIER_ROWS} />);

    const modelFilter = screen.getAllByRole("combobox")[0];
    fireEvent.change(modelFilter, { target: { value: "Газель" } });

    expect(screen.getByText("Стр. 1 из 1 (1 строк из 10)")).toBeInTheDocument();
  });

  it("для столбца с >30 уникальными значениями показывает текстовое поле", () => {
    const rows = [...Array(31)].map((_, i) => ({ model: `М${i}`, mileage: "1" }));

    render(<FilterableTable columns={COLUMNS} rows={rows} />);

    expect(screen.getByPlaceholderText("Фильтр...")).toBeInTheDocument();
  });
});

describe("FilterableTable: подсветка выбросов", () => {
  it("помечает выброс классом cell-outlier, обычные значения не помечаются", () => {
    render(<FilterableTable columns={COLUMNS} rows={OUTLIER_ROWS} />);

    // "100" есть и в ячейке таблицы, и в опциях фильтра — ищем именно ячейку.
    expect(screen.getByRole("cell", { name: "100" })).toHaveClass("cell-outlier");
    expect(screen.getAllByRole("cell", { name: "10" })[0]).not.toHaveClass("cell-outlier");
  });

  it("при highlightOutliers={false} выбросы не помечаются", () => {
    render(<FilterableTable columns={COLUMNS} rows={OUTLIER_ROWS} highlightOutliers={false} />);

    expect(screen.getByRole("cell", { name: "100" })).not.toHaveClass("cell-outlier");
  });
});

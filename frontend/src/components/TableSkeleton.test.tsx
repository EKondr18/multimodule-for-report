import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import TableSkeleton from "./TableSkeleton";

describe("TableSkeleton", () => {
  it("объявляется как status с подписью «Загрузка данных» для скринридеров", () => {
    render(<TableSkeleton />);

    expect(screen.getByRole("status", { name: "Загрузка данных" })).toBeInTheDocument();
  });

  it("по умолчанию рисует шапку и 6 строк по 5 столбцов", () => {
    const { container } = render(<TableSkeleton />);

    // 1 строка шапки + 6 строк данных, в каждой 5 ячеек
    expect(container.querySelectorAll(".table-skeleton-row")).toHaveLength(7);
    expect(container.querySelectorAll(".table-skeleton-cell")).toHaveLength(35);
  });

  it("принимает количество строк и столбцов из props", () => {
    const { container } = render(<TableSkeleton rows={2} columns={3} />);

    expect(container.querySelectorAll(".table-skeleton-row")).toHaveLength(3);
    expect(container.querySelectorAll(".table-skeleton-cell")).toHaveLength(9);
  });
});

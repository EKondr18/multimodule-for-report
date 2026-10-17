interface Props {
  /** Количество "строк"-плейсхолдеров. */
  rows?: number;
  /** Количество "столбцов"-плейсхолдеров. */
  columns?: number;
}

/**
 * Анимированный плейсхолдер в форме таблицы, показывается на месте будущей
 * таблицы, пока отчёт формируется. Используется вместо/вместе с текстовым
 * статусом — текстовые сообщения (например "Сервер просыпается…") всё
 * равно показываются отдельно, этот компонент только даёт визуальную
 * форму ожидания.
 */
export default function TableSkeleton({ rows = 6, columns = 5 }: Props) {
  return (
    <div className="table-skeleton" role="status" aria-label="Загрузка данных">
      <div className="table-skeleton-row table-skeleton-head">
        {Array.from({ length: columns }).map((_, i) => (
          <div key={i} className="table-skeleton-cell" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="table-skeleton-row">
          {Array.from({ length: columns }).map((_, c) => (
            <div key={c} className="table-skeleton-cell" />
          ))}
        </div>
      ))}
    </div>
  );
}

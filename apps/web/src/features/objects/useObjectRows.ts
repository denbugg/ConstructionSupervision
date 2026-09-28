import { useQueries, useQuery } from "@tanstack/react-query";

import { openDeviations } from "@/entities/status";
import { type ObjectRead, type ObjectStatus, objectsQuery, statusQuery } from "@/shared/api/queries";

export type ObjectRow = {
  object: ObjectRead;
  /** undefined — статус ещё грузится, null — прогона не было. */
  status: ObjectStatus | null | undefined;
  statusError: unknown;
  openDeviations: number | null;
};

/**
 * Строки списка: объект из plan и его статус из analysis. Статусы грузятся параллельно и
 * не задерживают список: объект виден сразу, статус дорисовывается.
 */
export function useObjectRows() {
  const objects = useQuery(objectsQuery);
  const items = objects.data?.items ?? [];
  const statuses = useQueries({ queries: items.map((o) => statusQuery(o.id)) });

  const rows: ObjectRow[] = items.map((object, i) => {
    const status = statuses[i]?.data;
    return {
      object,
      status,
      statusError: statuses[i]?.error ?? null,
      openDeviations: status ? openDeviations(status.deviations) : null,
    };
  });
  return { objects, rows };
}

/** Какие объекты показывать: действующие (черновики и в работе), архив или все. */
export type Scope = "current" | "archived" | "all";
export type Sort = "attention" | "name" | "start";

export function inScope(row: ObjectRow, scope: Scope): boolean {
  const archived = row.object.status === "ARCHIVED";
  return scope === "all" || (scope === "archived" ? archived : !archived);
}

/**
 * Список на экране: фильтр, поиск по названию и адресу, сортировка. «Сначала проблемные» —
 * отставание (больше — выше), затем высокая серьёзность, затем число открытых отклонений.
 */
export function visibleRows(rows: ObjectRow[], scope: Scope, query: string, sort: Sort): ObjectRow[] {
  const needle = query.trim().toLowerCase();
  const found = rows.filter(
    (row) =>
      inScope(row, scope) &&
      (!needle || `${row.object.name} ${row.object.address ?? ""}`.toLowerCase().includes(needle)),
  );
  const byName = (a: ObjectRow, b: ObjectRow) => a.object.name.localeCompare(b.object.name, "ru");
  const compare: Record<Sort, (a: ObjectRow, b: ObjectRow) => number> = {
    name: byName,
    start: (a, b) => (b.object.plan_start ?? "").localeCompare(a.object.plan_start ?? "") || byName(a, b),
    attention: (a, b) =>
      attention(b) - attention(a) ||
      (b.status?.delay_days ?? 0) - (a.status?.delay_days ?? 0) ||
      (b.status?.deviations.HIGH ?? 0) - (a.status?.deviations.HIGH ?? 0) ||
      (b.openDeviations ?? 0) - (a.openDeviations ?? 0) ||
      byName(a, b),
  };
  return [...found].sort(compare[sort]);
}

// Ступени внимания: отставание важнее высокой серьёзности, та — любых открытых.
function attention(row: ObjectRow): number {
  if (row.status?.status === "DELAY") return 3;
  if ((row.status?.deviations.HIGH ?? 0) > 0) return 2;
  if ((row.openDeviations ?? 0) > 0) return 1;
  return 0;
}

export type Summary = {
  current: number;
  delayed: number;
  open: number;
  high: number;
  notAnalyzed: number;
};

/** Сводка над списком — по действующим объектам: архив в ней только шумит. */
export function summarize(rows: ObjectRow[]): Summary {
  const current = rows.filter((row) => inScope(row, "current"));
  return {
    current: current.length,
    delayed: current.filter((row) => row.status?.status === "DELAY").length,
    open: current.reduce((sum, row) => sum + (row.openDeviations ?? 0), 0),
    high: current.reduce((sum, row) => sum + (row.status?.deviations.HIGH ?? 0), 0),
    notAnalyzed: current.filter((row) => row.status === null).length,
  };
}

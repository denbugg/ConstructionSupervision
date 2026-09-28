/**
 * Рабочие дни календаря объекта для правки дат на Ганте. Даты этапов в plan-service — рабочие дни
 * (methodology.md, §2), поэтому перетаскивание прилипает к ним, а сдвиг этапа целиком сохраняет
 * его длительность в рабочих днях, а не в календарных.
 */
import { isoDate } from "@/features/gantt/layout";

export type WorkCalendar = { weekend_days: number[]; holidays: string[] };

export type Dates = { start: number; end: number };

/** Как этап тянут: целиком, за левый край (начало) или за правый (конец). */
export type DragMode = "move" | "start" | "end";

// Предел поиска рабочего дня: больше двух недель подряд выходных в календаре не бывает,
// а испорченный календарь без рабочих дней не должен вешать вкладку.
const SEARCH_LIMIT = 60;
const EPOCH_ISO_WEEKDAY = 4; // 1970-01-01 — четверг

/** День недели по ISO: понедельник — 1, воскресенье — 7, как `weekend_days` в plan-service. */
const isoWeekday = (day: number) => ((((day + EPOCH_ISO_WEEKDAY - 1) % 7) + 7) % 7) + 1;

export function isWorkday(day: number, cal: WorkCalendar): boolean {
  return !cal.weekend_days.includes(isoWeekday(day)) && !cal.holidays.includes(isoDate(day));
}

/** Ближайший рабочий день в сторону `step` (+1 — вперёд, −1 — назад), включая сам день. */
export function snap(day: number, cal: WorkCalendar, step: 1 | -1): number {
  for (let d = day, i = 0; i < SEARCH_LIMIT; d += step, i++) {
    if (isWorkday(d, cal)) return d;
  }
  return day;
}

/** Рабочих дней в окне, обе границы включительно. */
export function workdaysIn({ start, end }: Dates, cal: WorkCalendar): number {
  let count = 0;
  for (let d = start; d <= end; d++) if (isWorkday(d, cal)) count++;
  return count;
}

/** Рабочий день, отстоящий от рабочего дня `day` на `n` рабочих дней вперёд. */
function addWorkdays(day: number, n: number, cal: WorkCalendar): number {
  let d = day;
  for (let left = n; left > 0; ) {
    d += 1;
    if (isWorkday(d, cal)) left--;
  }
  return d;
}

/**
 * Новые даты этапа после перетаскивания на `delta` календарных дней. Начало прилипает к рабочему
 * дню вперёд, конец — назад: край не уезжает на выходной. Конец не раньше начала.
 */
export function dragDates(from: Dates, mode: DragMode, delta: number, cal: WorkCalendar): Dates {
  if (mode === "move") {
    const start = snap(from.start + delta, cal, delta < 0 ? -1 : 1);
    return { start, end: addWorkdays(start, Math.max(workdaysIn(from, cal) - 1, 0), cal) };
  }
  if (mode === "start") {
    return { start: Math.min(snap(from.start + delta, cal, 1), from.end), end: from.end };
  }
  return { start: from.start, end: Math.max(snap(from.end + delta, cal, -1), from.start) };
}

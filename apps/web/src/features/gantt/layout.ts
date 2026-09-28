/**
 * Геометрия диаграммы Ганта: даты → пиксели, полосы, связи, шкала месяцев. Чистые функции без
 * React: экран только рисует то, что здесь посчитано.
 *
 * Даты плана — `YYYY-MM-DD` без пояса, обе границы этапа включительно. Внутри — номер дня от
 * эпохи (UTC), чтобы не зависеть от пояса браузера.
 */

const DAY_MS = 86_400_000;

export const ROW_HEIGHT = 36;
// Шапка — две строки: годы и месяцы. Подвал — подпись линии момента анализа.
export const HEADER_HEIGHT = 40;
export const FOOTER_HEIGHT = 22;
const BAR_HEIGHT = 18;
// Горизонтальный «локоть» связи до поворота вниз, px.
const LINK_STEP = 8;

export type Link = "FS" | "SS" | "FF" | "SF";

/** Номер дня от 1970-01-01 для даты плана. */
export function dayNumber(iso: string): number {
  return Math.round(Date.parse(`${iso.slice(0, 10)}T00:00:00Z`) / DAY_MS);
}

export function isoDate(day: number): string {
  return new Date(day * DAY_MS).toISOString().slice(0, 10);
}

/** Сутки момента анализа по Москве (UTC+3 без летнего времени) — день линии «на момент». */
export function moscowDay(moment: string): number {
  return Math.floor((Date.parse(moment) + 3 * 3_600_000) / DAY_MS);
}

export type Scale = { start: number; end: number; pxPerDay: number };

/**
 * Окно диаграммы: от начала месяца самой ранней даты до конца месяца самой поздней. Прогноз и
 * фактический старт тоже входят в окно — иначе хвост опоздания обрезался бы краем.
 */
export function makeScale(days: number[], pxPerDay: number): Scale {
  const first = new Date(Math.min(...days) * DAY_MS);
  const last = new Date(Math.max(...days) * DAY_MS);
  const start = Date.UTC(first.getUTCFullYear(), first.getUTCMonth(), 1) / DAY_MS;
  const end = Date.UTC(last.getUTCFullYear(), last.getUTCMonth() + 1, 1) / DAY_MS;
  return { start, end, pxPerDay };
}

export const width = (scale: Scale) => (scale.end - scale.start) * scale.pxPerDay;

/** Левый край дня. Конец этапа включительно, поэтому правый край полосы — `x(end + 1)`. */
export const x = (scale: Scale, day: number) => (day - scale.start) * scale.pxPerDay;

export const rowTop = (row: number) => HEADER_HEIGHT + row * ROW_HEIGHT;
export const barTop = (row: number) => rowTop(row) + (ROW_HEIGHT - BAR_HEIGHT) / 2;
export { BAR_HEIGHT };

export type Bar = { x: number; width: number; y: number };

export function bar(scale: Scale, row: number, startDay: number, endDay: number): Bar {
  const left = x(scale, startDay);
  return { x: left, width: Math.max(x(scale, endDay + 1) - left, 2), y: barTop(row) };
}

export type Tick = { x: number; label: string; year: number | null };

/**
 * Метки шкалы: начало каждого месяца, три буквы — на «весь график» месяц бывает уже 30 px.
 * Год — у января и у первой метки, отдельной строкой шапки.
 */
export function monthTicks(scale: Scale): Tick[] {
  const month = new Intl.DateTimeFormat("ru-RU", { timeZone: "UTC", month: "long" });
  const ticks: Tick[] = [];
  const cursor = new Date(scale.start * DAY_MS);
  while (cursor.getTime() / DAY_MS < scale.end) {
    const withYear = ticks.length === 0 || cursor.getUTCMonth() === 0;
    ticks.push({
      x: x(scale, cursor.getTime() / DAY_MS),
      label: month.format(cursor).slice(0, 3),
      year: withYear ? cursor.getUTCFullYear() : null,
    });
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  }
  return ticks;
}

/**
 * Путь стрелки связи между полосами. Тип связи задаёт концы: FS — конец предшественника →
 * начало последователя, SS — начало → начало, FF — конец → конец, SF — начало → конец.
 */
export function linkPath(type: Link, from: Bar, to: Bar): string {
  const fromX = type === "FS" || type === "FF" ? from.x + from.width : from.x;
  const toX = type === "FS" || type === "SS" ? to.x : to.x + to.width;
  const fromY = from.y + BAR_HEIGHT / 2;
  const toY = to.y + BAR_HEIGHT / 2;
  // К началу полосы стрелка подходит слева, к концу — справа.
  const entry = type === "FS" || type === "SS" ? toX - LINK_STEP : toX + LINK_STEP;
  const exit = fromX + (type === "FS" || type === "FF" ? LINK_STEP : -LINK_STEP);
  const midY = toY > fromY ? to.y - 3 : to.y + BAR_HEIGHT + 3;
  return `M ${fromX} ${fromY} H ${exit} V ${midY} H ${entry} V ${toY} H ${toX}`;
}

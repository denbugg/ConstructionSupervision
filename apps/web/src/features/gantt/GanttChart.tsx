import { useEffect, useRef, useState, type PointerEvent, type RefObject } from "react";

import { formatDelay, formatPlanDate } from "@/entities/format";
import { stageStatusFill } from "@/entities/status";
import {
  BAR_HEIGHT,
  FOOTER_HEIGHT,
  HEADER_HEIGHT,
  ROW_HEIGHT,
  bar,
  isoDate,
  linkPath,
  makeScale,
  monthTicks,
  rowTop,
  width,
  x,
  type Bar,
  type Scale,
} from "@/features/gantt/layout";
import { rowDays, type GanttRow } from "@/features/gantt/useGantt";
import { dragDates, type Dates, type DragMode, type WorkCalendar } from "@/features/gantt/workdays";
import { label, ru } from "@/shared/locale/ru";
import { Icon } from "@/shared/ui/Icon";

/** Масштаб: «весь график» подгоняется под ширину экрана, остальные — пикселей на день. */
export type Zoom = "fit" | number;

const MIN_FIT_PX = 0.5;

/** Несохранённые даты этапа: их задают перетаскивание и форма карточки. */
export type Draft = { stageId: string; dates: Dates };

type Props = {
  rows: GanttRow[];
  asOfDay: number | null;
  zoom: Zoom;
  selectedId: string | null;
  onSelect: (stageId: string) => void;
  draft: Draft | null;
  calendar: WorkCalendar;
  onDraft: (draft: Draft) => void;
};

type Drag = { stageId: string; mode: DragMode; originX: number; from: Dates };

/**
 * Диаграмма: слева этапы, справа SVG-сетка по дням. Полоса — плановое окно этапа, заливка —
 * фактический прогресс, треугольник — фактический старт, пунктирный хвост — прогноз позже плана.
 * Полосу можно тянуть целиком или за край: даты уходят в черновик, сохраняет карточка этапа.
 */
export function GanttChart(props: Props) {
  const { rows, asOfDay, zoom, selectedId, onSelect, draft, calendar, onDraft } = props;
  const scroller = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);
  const available = useWidth(scroller);
  const span = makeScale(rowDays(rows, asOfDay), 1);
  const pxPerDay =
    zoom === "fit" ? Math.max(available / (span.end - span.start), MIN_FIT_PX) : zoom;
  const scale: Scale = { ...span, pxPerDay };
  const datesOf = (r: GanttRow): Dates =>
    draft?.stageId === r.stage.id ? draft.dates : { start: r.start, end: r.end };
  const bars = new Map(
    rows.map((r, i) => [r.stage.id, bar(scale, i, datesOf(r).start, datesOf(r).end)]),
  );
  const height = HEADER_HEIGHT + rows.length * ROW_HEIGHT;

  const grab = (row: GanttRow, mode: DragMode, event: PointerEvent<SVGElement>) => {
    event.stopPropagation();
    event.currentTarget.ownerSVGElement?.setPointerCapture(event.pointerId);
    drag.current = { stageId: row.stage.id, mode, originX: event.clientX, from: datesOf(row) };
    onSelect(row.stage.id);
  };
  const move = (event: PointerEvent<SVGSVGElement>) => {
    const current = drag.current;
    if (!current) return;
    const delta = Math.round((event.clientX - current.originX) / pxPerDay);
    onDraft({ stageId: current.stageId, dates: dragDates(current.from, current.mode, delta, calendar) });
  };

  // При смене масштаба — к линии момента анализа: смотреть нужно туда, где «сейчас». Только по
  // масштабу: прокрутку, которую человек сделал сам, пересчёт данных сбрасывать не должен.
  useEffect(() => {
    const el = scroller.current;
    if (el && asOfDay != null) el.scrollLeft = x(scale, asOfDay) - el.clientWidth / 2;
  }, [pxPerDay]);

  return (
    <div className="flex overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-ink/[0.07]">
      <ul className="w-72 shrink-0 border-r border-ink/10 text-sm">
        <li style={{ height: HEADER_HEIGHT }} className="flex items-end border-b border-ink/10 px-3 pb-1.5 text-xs font-medium uppercase tracking-wide text-muted">
          Этап
        </li>
        {rows.map((r) => (
          <li key={r.stage.id} style={{ height: ROW_HEIGHT }}>
            <button
              type="button"
              onClick={() => onSelect(r.stage.id)}
              title={r.stage.name}
              className={`flex h-full w-full items-center gap-2 truncate px-3 text-left ${
                r.stage.id === selectedId ? "bg-accent/10" : "hover:bg-canvas"
              }`}
            >
              <span className={`shrink-0 font-medium ${r.stage.is_critical ? "text-accent" : ""}`}>
                {r.stage.code}
              </span>
              <span className="truncate">{r.stage.name}</span>
              {r.stage.completed_on && (
                <span className="ml-auto text-emerald-700" title="Выполнен по отметке оператора">
                  <Icon name="check" size={14} />
                  <span className="sr-only">выполнен по отметке</span>
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
      <div ref={scroller} className="min-w-0 flex-1 overflow-x-auto">
        <svg
          width={width(scale)}
          height={height + FOOTER_HEIGHT}
          className="block touch-none select-none text-xs"
          onPointerMove={move}
          onPointerUp={() => (drag.current = null)}
          onPointerCancel={() => (drag.current = null)}
        >
          <defs>
            <marker id="gantt-arrow" viewBox="0 0 6 6" refX="6" refY="3" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0,0 L6,3 L0,6 z" className="fill-stone-500" />
            </marker>
          </defs>
          <Grid scale={scale} rows={rows.length} height={height} />
          {rows.map((r, i) =>
            r.stage.id === selectedId ? (
              <rect key="selected" x={0} y={rowTop(i)} width={width(scale)} height={ROW_HEIGHT} className="fill-accent/10" />
            ) : null,
          )}
          {rows.flatMap((r) =>
            r.stage.predecessors.map((p) => {
              const from = bars.get(p.stage_id);
              const to = bars.get(r.stage.id);
              if (!from || !to) return null;
              return (
                <path
                  key={`${p.stage_id}-${r.stage.id}`}
                  d={linkPath(p.type, from, to)}
                  markerEnd="url(#gantt-arrow)"
                  className="fill-none stroke-stone-500"
                  strokeWidth={1}
                />
              );
            }),
          )}
          {rows.map((r, i) => (
            <StageBar
              key={r.stage.id}
              row={r}
              index={i}
              geometry={bars.get(r.stage.id)!}
              original={draft?.stageId === r.stage.id ? bar(scale, i, r.start, r.end) : null}
              scale={scale}
              onSelect={onSelect}
              onGrab={(mode, event) => grab(r, mode, event)}
            />
          ))}
          {asOfDay != null && (
            <AsOfLine x={x(scale, asOfDay + 1)} height={height} day={asOfDay} total={width(scale)} />
          )}
        </svg>
      </div>
    </div>
  );
}

function Grid({ scale, rows, height }: { scale: Scale; rows: number; height: number }) {
  return (
    <g>
      {Array.from({ length: rows }, (_, i) => (
        <line key={i} x1={0} x2={width(scale)} y1={rowTop(i + 1)} y2={rowTop(i + 1)} className="stroke-ink/5" />
      ))}
      {monthTicks(scale).map((tick) => (
        <g key={tick.x}>
          <line x1={tick.x} x2={tick.x} y1={tick.year ? 0 : 20} y2={height} className="stroke-ink/10" />
          {tick.year && (
            <text x={tick.x + 4} y={14} className="fill-ink font-medium">
              {tick.year}
            </text>
          )}
          <text x={tick.x + 3} y={33} className="fill-muted">
            {tick.label}
          </text>
        </g>
      ))}
      <line x1={0} x2={width(scale)} y1={HEADER_HEIGHT} y2={HEADER_HEIGHT} className="stroke-ink/10" />
    </g>
  );
}

// Ширина «ручки» края полосы, px: за неё тянется начало или конец.
const HANDLE = 6;

function StageBar({
  row,
  geometry,
  original,
  scale,
  index,
  onSelect,
  onGrab,
}: {
  row: GanttRow;
  geometry: Bar;
  /** Плановое окно до правки — пунктиром, пока даты в черновике. */
  original: Bar | null;
  scale: Scale;
  index: number;
  onSelect: (stageId: string) => void;
  onGrab: (mode: DragMode, event: PointerEvent<SVGElement>) => void;
}) {
  const { stage, progress } = row;
  const done = Math.min(Math.max(progress?.progress ?? 0, 0), 1);
  // Прогноз посчитан по сохранённым датам: пока полосу правят, хвост и «±N» не показываем.
  const fact = original == null;
  const late = fact && row.forecastEnd != null && row.forecastEnd > row.end;
  const early = fact && row.forecastEnd != null && row.forecastEnd < row.end;
  const tailEnd = row.forecastEnd != null ? x(scale, row.forecastEnd + 1) : 0;
  const planEnd = geometry.x + geometry.width;
  return (
    <g onClick={() => onSelect(stage.id)} className="cursor-pointer">
      <title>{tooltip(row)}</title>
      <rect x={0} y={rowTop(index)} width={width(scale)} height={ROW_HEIGHT} className="fill-transparent" />
      {original && (
        <rect
          x={original.x}
          y={original.y}
          width={original.width}
          height={BAR_HEIGHT}
          rx={3}
          className="fill-none stroke-ink/40"
          strokeDasharray="4 3"
        />
      )}
      <rect
        x={geometry.x}
        y={geometry.y}
        width={geometry.width}
        height={BAR_HEIGHT}
        rx={3}
        onPointerDown={(e) => onGrab("move", e)}
        className={`cursor-grab ${stage.is_critical ? "fill-accent/20 stroke-accent" : "fill-stone-200 stroke-stone-400"} ${
          original ? "stroke-2" : ""
        }`}
      />
      {done > 0 && (
        <rect
          x={geometry.x}
          y={geometry.y + 4}
          width={geometry.width * done}
          height={BAR_HEIGHT - 8}
          rx={2}
          onPointerDown={(e) => onGrab("move", e)}
          className={`cursor-grab ${stageStatusFill(progress?.status)}`}
        />
      )}
      <rect
        x={geometry.x - HANDLE / 2}
        y={geometry.y}
        width={HANDLE}
        height={BAR_HEIGHT}
        onPointerDown={(e) => onGrab("start", e)}
        className="cursor-ew-resize fill-transparent"
      />
      <rect
        x={planEnd - HANDLE / 2}
        y={geometry.y}
        width={HANDLE}
        height={BAR_HEIGHT}
        onPointerDown={(e) => onGrab("end", e)}
        className="cursor-ew-resize fill-transparent"
      />
      {late && (
        <rect
          x={planEnd}
          y={geometry.y + 3}
          width={Math.max(tailEnd - planEnd, 2)}
          height={BAR_HEIGHT - 6}
          className="fill-red-100 stroke-red-600"
          strokeDasharray="3 2"
        />
      )}
      {early && <line x1={tailEnd} x2={tailEnd} y1={geometry.y - 2} y2={geometry.y + BAR_HEIGHT + 2} className="stroke-sky-600" strokeWidth={2} />}
      {row.actualStart != null && (
        <path
          d={`M ${x(scale, row.actualStart) - 5} ${geometry.y - 7} h 10 l -5 7 z`}
          className="fill-ink"
        />
      )}
      {fact && progress?.delay_days != null && progress.delay_days !== 0 && (
        <text
          x={Math.max(planEnd, late ? tailEnd : planEnd) + 4}
          y={geometry.y + BAR_HEIGHT - 5}
          className={progress.delay_days > 0 ? "fill-red-700" : "fill-sky-700"}
        >
          {formatDelay(progress.delay_days)}
        </text>
      )}
    </g>
  );
}

function AsOfLine({ x: left, height, day, total }: { x: number; height: number; day: number; total: number }) {
  // Подпись не должна уходить за край: у краёв она прижимается к линии с внутренней стороны.
  const anchor = left < 120 ? "start" : left > total - 120 ? "end" : "middle";
  return (
    <g>
      <line x1={left} x2={left} y1={HEADER_HEIGHT} y2={height + 4} className="stroke-ink" strokeDasharray="4 3" />
      <text x={left} y={height + FOOTER_HEIGHT - 6} textAnchor={anchor} className="fill-ink font-medium">
        на момент анализа {formatPlanDate(isoDate(day))}
      </text>
    </g>
  );
}

/** Подсказка полосы: план, факт, прогноз одной строкой на каждое. */
function tooltip({ stage, progress }: GanttRow): string {
  const lines = [
    `${stage.code} ${stage.name}`,
    `План: ${formatPlanDate(stage.plan_start)} — ${formatPlanDate(stage.plan_end)}`,
    stage.is_critical ? "Критический путь" : `Резерв: ${stage.total_float_days} ${ru.units.workDays}`,
  ];
  if (stage.completed_on) {
    const by = stage.completed_by ? `, ${stage.completed_by}` : "";
    lines.push(`Выполнен по отметке: ${formatPlanDate(stage.completed_on)}${by}`);
  }
  if (progress) {
    lines.push(
      `${label(ru.stageStatus, progress.status)}, прогресс ${Math.round(progress.progress * 100)} % при плане ${Math.round(progress.planned_progress * 100)} %`,
      `Фактический старт: ${formatPlanDate(progress.actual_start)}`,
      `Прогноз окончания: ${formatPlanDate(progress.forecast_end)} (${formatDelay(progress.delay_days)} ${ru.units.workDays})`,
    );
  }
  return lines.join("\n");
}

/** Ширина области диаграммы — для масштаба «весь график». */
function useWidth(ref: RefObject<HTMLElement | null>): number {
  const [value, setValue] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setValue(el.clientWidth));
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return value;
}

import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { formatDelay, formatMoment, formatPlanDate, formatSpi } from "@/entities/format";
import { stageStatusTone } from "@/entities/status";
import { GanttChart, type Draft, type Zoom } from "@/features/gantt/GanttChart";
import { dayNumber, isoDate } from "@/features/gantt/layout";
import { SaveSummary } from "@/features/gantt/SaveSummary";
import { StageCompletion } from "@/features/gantt/StageCompletion";
import { useGantt, useSaveStage, useSelectedRow, type GanttRow, type Plan, type PlanStage } from "@/features/gantt/useGantt";
import { isWorkday, workdaysIn, type Dates } from "@/features/gantt/workdays";
import { hasGenerator, NO_GENERATOR_NOTE } from "@/features/objects/objectDraft";
import { PlanSetupDialog, type PlanMode } from "@/features/objects/PlanSetupDialog";
import { objectQuery } from "@/shared/api/queries";
import { label, ru } from "@/shared/locale/ru";
import { Badge } from "@/shared/ui/Badge";
import { Button, IconButton } from "@/shared/ui/Button";
import { fieldClass } from "@/shared/ui/Field";
import { Icon } from "@/shared/ui/Icon";
import { PageHeader, Segmented } from "@/shared/ui/Page";
import { Empty, ErrorBox, Loading } from "@/shared/ui/QueryState";
import { useToast } from "@/shared/ui/Toast";

// Этап закрыт отметкой оператора (stage_fact.facts.basis, methodology.md, 10.3b).
const OPERATOR = "OPERATOR";

const ZOOMS: { label: string; value: Zoom }[] = [
  { label: "Весь график", value: "fit" },
  { label: "Месяцы", value: 4 },
  { label: "Недели", value: 14 },
];

/**
 * Гант план-факт (F10): плановые окна этапов из plan-service, факт и прогноз из analysis-service.
 * Прогноз — при сохранении текущего темпа, с уверенностью (apps/web/README.md, §5).
 */
export function GanttScreen() {
  const { objectId = "" } = useParams();
  const object = useQuery(objectQuery(objectId));
  const { plan, progress, rows, asOfDay } = useGantt(objectId);
  const { selected, select } = useSelectedRow(rows);
  const [zoom, setZoom] = useState<Zoom>("fit");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [planMode, setPlanMode] = useState<PlanMode | null>(null);
  // Пока объект не загружен, кнопку расчёта не прячем: диалог всё равно откроется только с объектом.
  const generator = object.data ? hasGenerator(object.data.object_type) : true;
  const activeDraft = draft && draft.stageId === selected?.stage.id ? draft : null;
  // Черновик — только у выбранного этапа: переход к другому этапу его сбрасывает.
  const choose = (stageId: string) => {
    if (stageId !== selected?.stage.id) setDraft(null);
    select(stageId);
  };

  return (
    <div>
      <PageHeader
        title="График план-факт"
        description="Плановые окна этапов, фактический старт, выполнение и прогноз окончания. Полосу можно тянуть мышью — даты уйдут в черновик этапа."
        meta={
          plan.data &&
          rows.length > 0 && (
            <>
              <span>версия плана {plan.data.plan_version}</span>
              <span>·</span>
              <span>календарь {plan.data.calendar.code}</span>
              {progress.data && (
                <>
                  <span>·</span>
                  <span>анализ на {formatMoment(progress.data.as_of)}</span>
                </>
              )}
            </>
          )
        }
        actions={
          rows.length > 0 && (
            <>
              <Segmented size="sm" value={zoom} onChange={setZoom} options={ZOOMS} />
              <Button size="sm" icon="refresh" onClick={() => setPlanMode("generate")}>
                Перестроить
              </Button>
            </>
          )
        }
      />

      {plan.isPending && <Loading />}
      {plan.isError && <ErrorBox error={plan.error} onRetry={() => plan.refetch()} />}
      {progress.isError && <ErrorBox error={progress.error} onRetry={() => progress.refetch()} />}
      {plan.isSuccess && rows.length === 0 && (
        <Empty
          icon="gantt"
          title="У объекта нет графика"
          action={
            <>
              {generator && (
                <Button variant="primary" icon="sparkle" onClick={() => setPlanMode("generate")}>
                  Сгенерировать по МРР
                </Button>
              )}
              <Button variant={generator ? "secondary" : "primary"} icon="upload" onClick={() => setPlanMode("import")}>
                Импортировать CSV / XLSX
              </Button>
            </>
          }
        >
          {generator
            ? "Без графика не с чем сверять факт. Сгенерируйте его по нормам МРР-3.2.81-12 из этажности и площади или загрузите из файла — этапы придут вместе с правилами техники."
            : `Без графика не с чем сверять факт. ${NO_GENERATOR_NOTE}`}
        </Empty>
      )}
      {progress.data === null && rows.length > 0 && (
        <div className="mb-4 flex items-center gap-2 rounded-xl bg-sky-50 px-4 py-2.5 text-sm text-sky-900 ring-1 ring-sky-200">
          <Icon name="info" size={16} />
          Анализа по объекту ещё не было: показан только план, без факта и прогноза.
        </div>
      )}

      {plan.data && rows.length > 0 && (
        <div className="space-y-4">
          <GanttChart
            rows={rows}
            asOfDay={asOfDay}
            zoom={zoom}
            selectedId={selected?.stage.id ?? null}
            onSelect={choose}
            draft={activeDraft}
            calendar={plan.data.calendar}
            onDraft={setDraft}
          />
          <Legend />
          {selected ? (
            <StagePanel row={selected} stages={rows.map((r) => r.stage)} objectId={objectId} onClose={() => select(null)}>
              <DatesEditor
                key={selected.stage.id}
                objectId={objectId}
                row={selected}
                calendar={plan.data.calendar}
                draft={activeDraft}
                onDraft={setDraft}
              />
              <StageCompletion key={`done-${selected.stage.id}`} objectId={objectId} stage={selected.stage} asOfDay={asOfDay} />
            </StagePanel>
          ) : (
            <p className="flex items-center gap-2 text-sm text-muted">
              <Icon name="info" size={15} />
              Щёлкните по этапу — откроется его карточка с фактом, прогнозом и правкой дат.
            </p>
          )}
        </div>
      )}

      {planMode && object.data && (
        <PlanSetupDialog
          object={object.data}
          stages={rows.length}
          initialMode={planMode}
          open
          onClose={() => setPlanMode(null)}
        />
      )}
    </div>
  );
}

function Legend() {
  const item = (swatch: ReactNode, text: string) => (
    <span className="flex items-center gap-1.5">
      <svg width="22" height="12">
        {swatch}
      </svg>
      {text}
    </span>
  );
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1.5 rounded-xl bg-white/60 px-4 py-2.5 text-[13px] text-muted ring-1 ring-ink/[0.06]">
      {item(<rect x="1" y="1" width="20" height="10" rx="2" className="fill-stone-200 stroke-stone-400" />, "плановое окно")}
      {item(<rect x="1" y="1" width="20" height="10" rx="2" className="fill-accent/20 stroke-accent" />, "критический путь")}
      <div className="group relative inline-flex items-center gap-1.5 cursor-help">
        <svg width="26" height="12" className="shrink-0">
          <defs>
            <clipPath id="legend-status-clip">
              <rect x="1" y="3" width="24" height="6" rx="2" />
            </clipPath>
          </defs>
          <g clipPath="url(#legend-status-clip)">
            <rect x="1" y="3" width="6" height="6" className="fill-emerald-600" />
            <rect x="7" y="3" width="6" height="6" className="fill-amber-500" />
            <rect x="13" y="3" width="6" height="6" className="fill-red-600" />
            <rect x="19" y="3" width="6" height="6" className="fill-sky-600" />
          </g>
        </svg>
        <span className="border-b border-dotted border-muted/50 group-hover:border-ink/70">статус</span>
        <Icon name="info" size={13} className="text-muted/70 transition-colors group-hover:text-ink" />

        {/* Всплывающая подсказка с расшифровкой цветов */}
        <div className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 hidden w-64 -translate-x-1/2 rounded-xl bg-ink/95 p-3 text-xs text-white shadow-xl backdrop-blur-sm ring-1 ring-white/10 group-hover:block">
          <div className="mb-2 flex items-center justify-between border-b border-white/10 pb-1.5 font-medium text-white/90">
            <span>Цвета статуса этапа</span>
            <span className="text-[11px] font-normal text-white/50">доля 0–100 %</span>
          </div>
          <div className="space-y-1.5 text-[12px]">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 rounded-sm bg-emerald-600" />
              <span className="font-medium text-white">Завершён</span>
              <span className="ml-auto text-[11px] text-white/60">100 %</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 rounded-sm bg-amber-500" />
              <span className="font-medium text-white">В работе</span>
              <span className="ml-auto text-[11px] text-white/60">в графике</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 rounded-sm bg-red-600" />
              <span className="font-medium text-white">С опозданием</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 rounded-sm bg-sky-600" />
              <span className="font-medium text-white">С опережением</span>
            </div>
          </div>
          <div className="mt-2 border-t border-white/10 pt-1.5 text-[11px] leading-tight text-white/60">
            Длина полосы показывает физический прогресс (выполненную долю).
          </div>
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-ink/95" />
        </div>
      </div>
      {item(<path d="M6 1 h10 l-5 7 z" className="fill-ink" />, "фактический старт")}
      {item(<rect x="1" y="2" width="20" height="8" className="fill-red-100 stroke-red-600" strokeDasharray="3 2" />, "прогноз позже плана")}
      {item(<line x1="11" x2="11" y1="0" y2="12" className="stroke-sky-600" strokeWidth="2" />, "прогноз раньше плана")}
      <span>±N — отставание в {ru.units.workDays}</span>
    </div>
  );
}

function StagePanel({
  row,
  stages,
  objectId,
  onClose,
  children,
}: {
  row: GanttRow;
  stages: PlanStage[];
  objectId: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const { stage, progress } = row;
  const names = new Map(stages.map((s) => [s.id, `${s.code} ${s.name}`]));
  const facts = (progress?.facts ?? {}) as Record<string, unknown>;
  return (
    <article className="animate-fade-in rounded-2xl bg-white shadow-sm ring-1 ring-ink/[0.07]">
      <header className="flex flex-wrap items-start gap-3 border-b border-ink/[0.07] px-6 py-4">
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold">
            <span className={stage.is_critical ? "text-accent" : "text-muted"}>{stage.code}</span> {stage.name}
          </h2>
          <p className="text-sm text-muted">
            {label(ru.stagePhase, stage.phase)} · по плану {formatPlanDate(stage.plan_start)} —{" "}
            {formatPlanDate(stage.plan_end)}, норма {stage.norm_duration_days} {ru.units.workDays}
          </p>
        </div>
        {progress && <Badge tone={stageStatusTone(progress.status)}>{label(ru.stageStatus, progress.status)}</Badge>}
        <Link
          to={`/objects/${objectId}/settings/rules?stage=${stage.id}`}
          className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium text-ink/75 hover:bg-ink/[0.06]"
        >
          <Icon name="rules" size={15} />
          Правило техники
        </Link>
        <IconButton icon="x" label="Закрыть карточку" size="sm" onClick={onClose} />
      </header>
      <div className="grid gap-6 p-6 lg:grid-cols-2">
        <div className="space-y-3 text-sm">
          <p className={`rounded-xl p-3 ${stage.is_critical ? "bg-accent/[0.06]" : stage.total_float_days < 0 ? "bg-red-50" : "bg-canvas/60"}`}>
            {stage.is_critical
              ? "На критическом пути: задержка этапа сдвигает окончание объекта."
              : stage.total_float_days < 0
                ? `Резерв ${formatDelay(stage.total_float_days)} ${ru.units.workDays}: даты этапа нарушают связи с соседями.`
                : `Резерв ${stage.total_float_days} ${ru.units.workDays}: на столько этап может сдвинуться без сдвига объекта.`}
          </p>
          {stage.basis && <p className="text-muted">Основание срока: {stage.basis}</p>}
          {stage.predecessors.length > 0 && (
            <div>
              <p className="mb-1 text-[13px] font-medium">Зависит от</p>
              <ul className="space-y-0.5">
                {stage.predecessors.map((p) => (
                  <li key={p.stage_id} className="flex gap-2">
                    <Icon name="chevronRight" size={14} className="mt-0.5 text-muted" />
                    <span>
                      {names.get(p.stage_id) ?? p.stage_id} — <span className="text-muted">{label(ru.linkType, p.type)}</span>
                      {p.lag_days !== 0 && `, лаг ${p.lag_days} ${ru.units.workDays}`}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="space-y-3 text-sm">
          {!progress ? (
            <p className="text-muted">Факта по этапу нет: анализ его ещё не считал.</p>
          ) : (
            <>
              <div>
                <div className="flex items-baseline justify-between">
                  <span className="text-muted">Выполнено</span>
                  <span>
                    <b className="text-lg tabular-nums">{Math.round(progress.progress * 100)} %</b>
                    <span className="text-muted"> при плане {Math.round(progress.planned_progress * 100)} %</span>
                  </span>
                </div>
                <div className="relative mt-1.5 h-2 rounded-full bg-ink/[0.07]">
                  <div className="h-full rounded-full bg-emerald-600" style={{ width: `${Math.round(progress.progress * 100)}%` }} />
                  <div className="absolute -top-1 h-4 w-0.5 rounded bg-ink/70" style={{ left: `${Math.round(progress.planned_progress * 100)}%` }} />
                </div>
              </div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
                <dt className="text-muted">Фактический старт</dt>
                <dd>{formatPlanDate(progress.actual_start)}</dd>
                <dt className="text-muted">SPI</dt>
                <dd className="tabular-nums">{formatSpi(progress.spi)}</dd>
                <dt className="text-muted">Прогноз окончания</dt>
                <dd>
                  {formatPlanDate(progress.forecast_end)}
                  {progress.delay_days != null && progress.delay_days !== 0 && (
                    <b className={progress.delay_days > 0 ? "text-red-700" : "text-sky-700"}>
                      {" "}
                      ({formatDelay(progress.delay_days)} {ru.units.workDays})
                    </b>
                  )}
                  <span className="block text-xs text-muted">
                    {facts.basis === OPERATOR ? "по отметке оператора" : "при сохранении текущего темпа"} · уверенность{" "}
                    {label(ru.confidence, progress.confidence)}
                  </span>
                </dd>
              </dl>
              <p className="text-xs text-muted">{basis(facts)}</p>
            </>
          )}
        </div>
        <div className="space-y-4 lg:col-span-2">{children}</div>
      </div>
    </article>
  );
}

/**
 * Правка плановых дат этапа (F11): черновик общий с перетаскиванием на диаграмме, сохранение —
 * PATCH этапа и прогон анализа, затем «было → стало» по прогнозу этапа и отставанию объекта.
 */
function DatesEditor({
  objectId,
  row,
  calendar,
  draft,
  onDraft,
}: {
  objectId: string;
  row: GanttRow;
  calendar: Plan["calendar"];
  draft: Draft | null;
  onDraft: (draft: Draft | null) => void;
}) {
  const save = useSaveStage(objectId);
  const toast = useToast();
  const dates = draft?.dates ?? { start: row.start, end: row.end };
  const set = (edge: keyof Dates, value: string) => {
    if (value) onDraft({ stageId: row.stage.id, dates: { ...dates, [edge]: dayNumber(value) } });
  };
  const issues = [
    dates.end < dates.start && "окончание раньше начала",
    !isWorkday(dates.start, calendar) && "начало — нерабочий день",
    !isWorkday(dates.end, calendar) && "окончание — нерабочий день",
  ].filter((issue): issue is string => typeof issue === "string");

  return (
    <div className={`space-y-3 rounded-xl p-4 text-sm ring-1 ${draft ? "bg-accent/[0.04] ring-accent/30" : "bg-canvas/50 ring-ink/[0.06]"}`}>
      <p className="flex items-center gap-2 font-medium">
        <Icon name="calendar" size={16} className="text-muted" />
        Плановые даты
        {draft && <Badge tone="bg-accent/10 text-accent ring-1 ring-inset ring-accent/25" size="sm">черновик</Badge>}
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Начало</span>
          <input type="date" value={isoDate(dates.start)} onChange={(e) => set("start", e.target.value)} className={fieldClass("input", "md", "w-auto")} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Окончание, включительно</span>
          <input type="date" value={isoDate(dates.end)} onChange={(e) => set("end", e.target.value)} className={fieldClass("input", "md", "w-auto")} />
        </label>
        <p className="pb-2 text-muted">
          {dates.end >= dates.start ? `${workdaysIn(dates, calendar)} ${ru.units.workDays}` : "—"} по календарю {calendar.code}
        </p>
        <div className="ml-auto flex gap-2">
          {draft && !save.isPending && (
            <Button variant="ghost" onClick={() => onDraft(null)}>
              Отменить
            </Button>
          )}
          <Button
            variant="primary"
            icon="check"
            disabled={!draft || issues.length > 0}
            loading={save.isPending}
            onClick={() =>
              save.mutate(
                { stageId: row.stage.id, patch: { plan_start: isoDate(dates.start), plan_end: isoDate(dates.end) } },
                {
                  onSuccess: () => {
                    onDraft(null);
                    toast.success("Даты этапа сохранены", "Анализ пересчитан — итог ниже");
                  },
                  onError: (error) => toast.error(error, "Даты не сохранены"),
                },
              )
            }
          >
            {save.isPending ? "Сохраняем и пересчитываем…" : "Сохранить и пересчитать"}
          </Button>
        </div>
      </div>
      {issues.length > 0 && <p className="text-red-700">Не сохранить: {issues.join("; ")}.</p>}
      <p className="text-xs text-muted">
        Полосу можно тянуть на диаграмме: целиком — длительность в рабочих днях сохраняется, за
        край — меняется начало или конец. Соседние этапы не сдвигаются: нарушенную связь покажет
        отрицательный резерв.
      </p>
      {save.data && <SaveSummary result={save.data} />}
    </div>
  );
}

/** Откуда прогресс этапа: отметка оператора, план (и почему) или наблюдения (сколько дней). */
function basis(facts: Record<string, unknown>): string {
  if (facts.basis === OPERATOR) {
    const on = typeof facts.completed_on === "string" ? formatPlanDate(facts.completed_on) : "—";
    const by = typeof facts.completed_by === "string" ? `, отметил ${facts.completed_by}` : "";
    return `Выполнен по отметке оператора: последний день работ ${on}${by}. Окончание подтвердил человек, а не снимки.`;
  }
  if (typeof facts.basis_reason === "string") return `Прогресс по плану: ${facts.basis_reason}.`;
  if (facts.basis === "OBSERVED") {
    const days = typeof facts.observed_days === "number" ? facts.observed_days : "—";
    const since = typeof facts.observation_start === "string" ? facts.observation_start : null;
    return `Прогресс по наблюдениям: дней наблюдений ${days}${since ? ` с ${formatPlanDate(since)}` : ""}.`;
  }
  return "";
}

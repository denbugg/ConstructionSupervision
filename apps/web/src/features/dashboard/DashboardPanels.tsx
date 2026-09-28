import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { formatDelay, formatMoment, formatPlanDate } from "@/entities/format";
import { severityDot, stageStatusBar } from "@/entities/status";
import {
  stagesAtRisk,
  useActiveStages,
  useLatestImages,
  useRecompute,
  useSetupSteps,
  useTopDeviations,
  type SetupStep,
} from "@/features/dashboard/useDashboard";
import { PlanSetupDialog } from "@/features/objects/PlanSetupDialog";
import { camerasQuery, type ObjectRead, type ObjectStatus } from "@/shared/api/queries";
import { label, ru } from "@/shared/locale/ru";
import { Dot } from "@/shared/ui/Badge";
import { Button, ButtonLink } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { Panel } from "@/shared/ui/Page";
import { ErrorBox, Loading } from "@/shared/ui/QueryState";
import { useToast } from "@/shared/ui/Toast";

const STEP_TEXT: Record<SetupStep["key"], { title: string; text: string }> = {
  plan: { title: "График работ", text: "Этапы и сроки — по нормам МРР или из файла" },
  images: { title: "Снимки с камер", text: "Папка на камеру: камеры заведутся сами" },
  zones: { title: "Зоны на камерах", text: "Где котлован, въезд, склад — чтобы относить технику к участкам" },
  analysis: { title: "Первый анализ", text: "Сверка план-факт; дальше запускается сам" },
};

/** Чек-лист подготовки: пока объект не готов, на каждый недостающий шаг — кнопка. */
export function SetupChecklist({ object }: { object: ObjectRead }) {
  const { loaded, steps, stages } = useSetupSteps(object.id);
  const [planning, setPlanning] = useState(false);
  const recompute = useRecompute(object.id, null);
  const toast = useToast();
  const done = steps.filter((s) => s.done).length;
  if (!loaded || done === steps.length) return null;
  const base = `/objects/${object.id}`;
  const next = steps.find((s) => !s.done)?.key;

  const action = (key: SetupStep["key"]) => {
    const variant = key === next ? "primary" : "secondary";
    switch (key) {
      case "plan":
        return <Button size="sm" variant={variant} icon="sparkle" onClick={() => setPlanning(true)}>Построить график</Button>;
      case "images":
        return <ButtonLink size="sm" variant={variant} icon="upload" to={`${base}/upload`}>Загрузить снимки</ButtonLink>;
      case "zones":
        return <ButtonLink size="sm" variant={variant} icon="zones" to={`${base}/settings/zones`}>Разметить зоны</ButtonLink>;
      case "analysis":
        return (
          <Button
            size="sm"
            variant={variant}
            icon="play"
            loading={recompute.isPending}
            onClick={() =>
              recompute.mutate(undefined, {
                onSuccess: () => toast.success("Анализ выполнен"),
                onError: (error) => toast.error(error, "Анализ не выполнен"),
              })
            }
          >
            Запустить анализ
          </Button>
        );
    }
  };

  return (
    <Panel
      title="Подготовка объекта"
      description={`Готово ${done} из ${steps.length}: без этих шагов выводов не будет`}
      icon="rules"
      bodyClassName="p-2"
    >
      <div className="mx-3 mb-2 mt-1 h-1.5 overflow-hidden rounded-full bg-ink/[0.06]">
        <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${(done / steps.length) * 100}%` }} />
      </div>
      <ol className="grid gap-1 md:grid-cols-2 xl:grid-cols-4">
        {steps.map((step, i) => (
          <li key={step.key} className={`flex flex-col gap-2 rounded-xl p-3 ${step.key === next ? "bg-accent/[0.05]" : ""}`}>
            <div className="flex items-start gap-2.5">
              <span
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                  step.done ? "bg-emerald-600 text-white" : "bg-ink/[0.07] text-ink/70"
                }`}
              >
                {step.done ? <Icon name="check" size={13} /> : i + 1}
              </span>
              <div>
                <p className={`text-sm font-medium ${step.done ? "text-muted line-through" : ""}`}>{STEP_TEXT[step.key].title}</p>
                <p className="text-xs text-muted">{STEP_TEXT[step.key].text}</p>
              </div>
            </div>
            {!step.done && <div className="pl-8">{action(step.key)}</div>}
          </li>
        ))}
      </ol>
      {planning && <PlanSetupDialog object={object} stages={stages} open onClose={() => setPlanning(false)} />}
    </Panel>
  );
}

/** Что разобрать первым: открытые отклонения по серьёзности, ссылка — прямо на карточку. */
export function AttentionPanel({ objectId }: { objectId: string }) {
  const { feed, items, total } = useTopDeviations(objectId);
  const base = `/objects/${objectId}/deviations`;
  return (
    <Panel
      className="lg:col-span-2"
      title="Требует внимания"
      description="Открытые предупреждения: сначала высокой серьёзности"
      icon="alert"
      bodyClassName="p-2"
      actions={
        total > items.length && (
          <ButtonLink to={`${base}?status=open`} size="sm" variant="ghost">
            Все {total} <Icon name="arrowRight" size={14} />
          </ButtonLink>
        )
      }
    >
      {feed.isPending && <div className="px-3"><Loading /></div>}
      {feed.isError && <div className="p-3"><ErrorBox error={feed.error} /></div>}
      {feed.isSuccess && items.length === 0 && (
        <div className="flex items-center gap-3 px-4 py-6 text-sm text-muted">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-50 text-emerald-700">
            <Icon name="check" size={16} />
          </span>
          Открытых предупреждений нет — объект идёт без нарушений правил.
        </div>
      )}
      <ul>
        {items.map((d) => (
          <li key={d.id}>
            <Link
              to={`${base}?status=open&id=${d.id}`}
              className="group flex items-start gap-3 rounded-xl px-3 py-2.5 hover:bg-canvas/70"
            >
              <Dot className={`mt-1.5 ${severityDot(d.severity)}`} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium group-hover:text-accent">{d.title}</p>
                <p className="text-xs text-muted">
                  {d.code} · {label(ru.deviationCode, d.code)} · {label(ru.severity, d.severity).toLowerCase()} · с{" "}
                  {formatMoment(d.first_seen_at)}
                </p>
              </div>
              <Icon name="chevronRight" size={16} className="mt-1 text-muted opacity-0 group-hover:opacity-100" />
            </Link>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

const STAGE_KEYS = ["done", "in_progress", "late", "ahead", "not_started"] as const;

/** Этапы по статусам одной полосой и этапы критического пути с прогнозом позже плана. */
export function StagesPanel({ objectId, status }: { objectId: string; status: ObjectStatus }) {
  const total = status.stages.total ?? 0;
  const risk = stagesAtRisk(status.stages_at_risk);
  return (
    <Panel title={`Этапы: ${total}`} icon="gantt" bodyClassName="p-5 space-y-4" actions={
      <ButtonLink to={`/objects/${objectId}/gantt`} size="sm" variant="ghost">Гант <Icon name="arrowRight" size={14} /></ButtonLink>
    }>
      {total > 0 && (
        <div>
          <div className="flex h-2.5 overflow-hidden rounded-full bg-ink/[0.06]">
            {STAGE_KEYS.map((key) => {
              const n = status.stages[key] ?? 0;
              return n > 0 ? (
                <span key={key} className={stageStatusBar(key.toUpperCase())} style={{ width: `${(n / total) * 100}%` }} title={`${label(ru.stageFactStatus, key.toUpperCase())}: ${n}`} />
              ) : null;
            })}
          </div>
          <ul className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
            {STAGE_KEYS.filter((key) => (status.stages[key] ?? 0) > 0).map((key) => (
              <li key={key} className="flex items-center gap-2">
                <Dot className={stageStatusBar(key.toUpperCase())} />
                <span className="text-muted">{label(ru.stageFactStatus, key.toUpperCase())}</span>
                <span className="ml-auto font-medium tabular-nums">{status.stages[key]}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <p className="mb-1.5 text-[13px] font-medium">В риске</p>
        {risk.length === 0 ? (
          <p className="text-sm text-muted">Этапов критического пути с прогнозом позже плана нет.</p>
        ) : (
          <ul className="space-y-1">
            {risk.map((stage) => (
              <li key={stage.stageId}>
                <Link
                  to={`/objects/${objectId}/gantt?stage=${stage.stageId}`}
                  className="group -mx-2 flex items-start gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-canvas/70"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate group-hover:text-accent">{stage.name}</span>
                    <span className="text-xs text-muted">
                      план {formatPlanDate(stage.planEnd)} → прогноз {formatPlanDate(stage.forecastEnd)}
                    </span>
                  </span>
                  <span className="font-medium tabular-nums text-red-700">{formatDelay(stage.delayDays)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}

/** Ход работ: этапы, которые идут сейчас, — выполнено против плана на момент анализа. */
export function ActiveStagesPanel({ objectId }: { objectId: string }) {
  const { isPending, active } = useActiveStages(objectId);
  if (isPending || active.length === 0) return null;
  return (
    <Panel title="Ход работ" description="Этапы в работе: выполнено против плана на момент анализа" icon="layers" bodyClassName="px-5 py-3">
      <ul className="divide-y divide-ink/[0.06]">
        {active.map(({ stage, progress }) => {
          const done = Math.round(progress.progress * 100);
          const planned = Math.round(progress.planned_progress * 100);
          return (
            <li key={stage.id}>
              <Link to={`/objects/${objectId}/gantt?stage=${stage.id}`} className="group grid items-center gap-x-6 gap-y-1 py-2.5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_13rem]">
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium group-hover:text-accent">
                    <span className={stage.is_critical ? "text-accent" : "text-muted"}>{stage.code}</span> {stage.name}
                  </span>
                  <span className="text-xs text-muted">
                    план {formatPlanDate(stage.plan_start)} — {formatPlanDate(stage.plan_end)}
                  </span>
                </span>
                <span className="relative h-2 rounded-full bg-ink/[0.07]" title={`Выполнено ${done} %, по плану ${planned} %`}>
                  <span className={`absolute inset-y-0 left-0 rounded-full ${stageStatusBar(progress.status)}`} style={{ width: `${done}%` }} />
                  <span className="absolute -top-1 h-4 w-0.5 rounded bg-ink/70" style={{ left: `${planned}%` }} />
                </span>
                <span className="text-right text-sm tabular-nums">
                  <span className="font-medium">{done} %</span>
                  <span className="text-muted"> из {planned} %</span>
                  {progress.delay_days != null && progress.delay_days > 0 && (
                    <span className="ml-2 font-medium text-red-700">{formatDelay(progress.delay_days)} {ru.units.workDays}</span>
                  )}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

export function LatestImagesPanel({ objectId }: { objectId: string }) {
  const latest = useLatestImages(objectId);
  const cameras = useQuery(camerasQuery(objectId));
  // Экран камер выбирает снимок внутри камеры: ссылке нужен и код камеры.
  const cameraCode = new Map((cameras.data?.items ?? []).map((c) => [c.id, c.code]));
  if (!latest.isPending && latest.error == null && latest.total === 0) return null;
  return (
    <Panel
      title="Последние снимки"
      icon="image"
      bodyClassName="p-5"
      actions={
        <ButtonLink to={`/objects/${objectId}/cameras`} size="sm" variant="ghost">
          Все камеры <Icon name="arrowRight" size={14} />
        </ButtonLink>
      }
    >
      {latest.isPending && <Loading />}
      {latest.error != null && <ErrorBox error={latest.error} />}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {latest.images.map((image) => (
          <Link
            key={image.id}
            to={`/objects/${objectId}/cameras?camera=${cameraCode.get(image.camera_id) ?? ""}&image=${image.id}`}
            className="group space-y-1.5"
          >
            <div className="overflow-hidden rounded-xl bg-ink/5 ring-1 ring-ink/[0.07]">
              <img
                src={image.url}
                alt={`Снимок ${formatMoment(image.captured_at)}`}
                className="aspect-video w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
              />
            </div>
            <p className="text-xs text-muted">
              {formatMoment(image.captured_at)} · рамок: {image.detections.length}
              {image.usable === false && ` · непригоден (${image.usable_reason ?? "?"})`}
            </p>
          </Link>
        ))}
      </div>
    </Panel>
  );
}

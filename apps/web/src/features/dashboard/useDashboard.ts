import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";

import { severityRank } from "@/entities/status";
import { planQuery, progressQuery } from "@/features/gantt/useGantt";
import { apiGet, apiPost } from "@/shared/api/client";
import {
  areasQuery,
  deviationsQuery,
  imageCountQuery,
  objectQuery,
  statusQuery,
  type DeviationFilter,
  type DeviationRead,
} from "@/shared/api/queries";
import type { AnalysisSchema, PlanSchema, SiteSchema } from "@/shared/api/schemas";

/** Сколько последних снимков показывать на обзоре. */
const LATEST_IMAGES = 4;
/** Сколько открытых отклонений показывать в «требует внимания». */
const TOP_DEVIATIONS = 5;

export type StageAtRisk = {
  stageId: string;
  name: string;
  planEnd: string | null;
  forecastEnd: string | null;
  delayDays: number | null;
};

/**
 * Этапы в риске приходят объектами без схемы (`stages_at_risk: object[]`), поэтому поля
 * разбираются здесь с проверкой типа, а не приведением: неизвестная форма даст прочерк.
 */
export function stagesAtRisk(items: ReadonlyArray<Record<string, unknown>>): StageAtRisk[] {
  const text = (v: unknown) => (typeof v === "string" ? v : null);
  const number = (v: unknown) => (typeof v === "number" ? v : null);
  return items.map((item) => ({
    stageId: text(item.stage_id) ?? "",
    name: text(item.name) ?? "—",
    planEnd: text(item.plan_end),
    forecastEnd: text(item.forecast_end),
    delayDays: number(item.delay_days),
  }));
}

export function useDashboard(objectId: string) {
  const object = useQuery(objectQuery(objectId));
  const status = useQuery(statusQuery(objectId));
  return { object, status };
}

/** Открытые — то, что ждёт решения оператора; тот же ключ кэша, что у ленты с этим фильтром. */
export const OPEN_FILTER: DeviationFilter = {
  codes: [],
  severities: [],
  statuses: ["NEW", "CONFIRMED"],
  verdicts: [],
  from: null,
  to: null,
};

/** Самые важные открытые отклонения: по серьёзности, внутри — свежие сверху. */
export function useTopDeviations(objectId: string) {
  const feed = useQuery(deviationsQuery(objectId, OPEN_FILTER));
  const items = [...(feed.data?.items ?? [])].sort(
    (a: DeviationRead, b: DeviationRead) =>
      severityRank(a.severity) - severityRank(b.severity) || b.last_seen_at.localeCompare(a.last_seen_at),
  );
  return { feed, items: items.slice(0, TOP_DEVIATIONS), total: feed.data?.total ?? 0 };
}

export type SetupStep = { key: "plan" | "images" | "zones" | "analysis"; done: boolean };

/**
 * Готов ли объект к работе: график, снимки, зоны, первый анализ. Пока хоть одного шага нет,
 * обзор показывает чек-лист с кнопкой на каждый шаг — новый объект не остаётся «пустым».
 */
export function useSetupSteps(objectId: string) {
  const plan = useQuery(planQuery(objectId));
  const images = useQuery(imageCountQuery(objectId));
  const areas = useQuery(areasQuery(objectId));
  const status = useQuery(statusQuery(objectId));
  const loaded = plan.isSuccess && images.isSuccess && areas.isSuccess && status.isSuccess;
  const steps: SetupStep[] = [
    { key: "plan", done: (plan.data?.stages.length ?? 0) > 0 },
    { key: "images", done: (images.data ?? 0) > 0 },
    { key: "zones", done: (areas.data?.areas.length ?? 0) > 0 },
    { key: "analysis", done: status.data != null },
  ];
  return { loaded, steps, stages: plan.data?.stages.length ?? 0 };
}

export type ActiveStage = {
  stage: PlanSchema<"PlanStage">;
  progress: AnalysisSchema<"StageProgress">;
};

/** Этапы, которые идут сейчас: в работе или с опозданием, — ход работ на обзоре. */
export function useActiveStages(objectId: string) {
  const plan = useQuery(planQuery(objectId));
  const progress = useQuery(progressQuery(objectId));
  const byStage = new Map((progress.data?.stages ?? []).map((p) => [p.stage_id, p]));
  const active: ActiveStage[] = (plan.data?.stages ?? []).flatMap((stage) => {
    const fact = byStage.get(stage.id);
    return fact && (fact.status === "IN_PROGRESS" || fact.status === "LATE") ? [{ stage, progress: fact }] : [];
  });
  return { isPending: plan.isPending || progress.isPending, active };
}

/**
 * Пересчёт по кнопке: прогон с ожиданием, затем свежие выводы на всех экранах.
 *
 * Считается на тот же момент `as_of`, что и показанный статус: кнопка отвечает на вопрос
 * «что изменилось после правки настроек», а не сдвигает момент анализа. Без статуса момент
 * выбирает analysis.
 */
export function useRecompute(objectId: string, asOf: string | null | undefined) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiPost<AnalysisSchema<"RunRead">>("/analysis/runs?wait=true", {
        object_id: objectId,
        triggered_by: "MANUAL",
        as_of: asOf ?? null,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["analysis"] }),
  });
}

/**
 * Последние снимки объекта. Список отдаётся по возрастанию времени съёмки, поэтому сначала
 * берётся общее число, затем хвост; ссылка на файл есть только в карточке снимка.
 */
export function useLatestImages(objectId: string) {
  const base = `/site/images?object_id=${objectId}&status=ANALYZED`;
  const count = useQuery({
    queryKey: ["site", "images", objectId, "count"],
    queryFn: ({ signal }) => apiGet<SiteSchema<"Page_ImageRead_">>(`${base}&limit=1`, signal),
  });
  const total = count.data?.total ?? 0;
  const tail = useQuery({
    queryKey: ["site", "images", objectId, "tail", total],
    enabled: total > 0,
    queryFn: ({ signal }) =>
      apiGet<SiteSchema<"Page_ImageRead_">>(
        `${base}&limit=${LATEST_IMAGES}&offset=${Math.max(0, total - LATEST_IMAGES)}`,
        signal,
      ),
  });
  const ids = [...(tail.data?.items ?? [])].reverse().map((i) => i.id);
  const details = useQueries({
    queries: ids.map((id) => ({
      queryKey: ["site", "image", id],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        apiGet<SiteSchema<"ImageDetail">>(`/site/images/${id}`, signal),
    })),
  });
  return {
    isPending: count.isPending || (total > 0 && tail.isPending),
    error: count.error ?? tail.error,
    total,
    images: details.flatMap((d) => (d.data ? [d.data] : [])),
  };
}

import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { dayNumber, moscowDay } from "@/features/gantt/layout";
import { ApiError, apiGet, apiPatch, apiPost } from "@/shared/api/client";
import { fetchStatus, type ObjectStatus } from "@/shared/api/queries";
import type { AnalysisSchema, PlanSchema } from "@/shared/api/schemas";

export type Plan = PlanSchema<"Plan">;
export type PlanStage = PlanSchema<"PlanStage">;
export type Progress = AnalysisSchema<"ProgressRead">;
export type StageProgress = AnalysisSchema<"StageProgress">;

/** Этап на диаграмме: план из plan-service и факт с прогнозом из analysis, если он есть. */
export type GanttRow = {
  stage: PlanStage;
  progress: StageProgress | null;
  start: number;
  end: number;
  actualStart: number | null;
  forecastEnd: number | null;
};

/** «Весь план» объекта: этапы по `seq`, связи, критический путь, календарь. */
export function planQuery(objectId: string) {
  return queryOptions({
    queryKey: ["plan", "plan", objectId],
    queryFn: ({ signal }) => apiGet<Plan>(`/plan/objects/${objectId}/plan`, signal),
  });
}

/** Факт и прогноз по этапам; `null` — анализа ещё не было, диаграмма показывает только план. */
export function progressQuery(objectId: string) {
  return queryOptions({
    queryKey: ["analysis", "progress", objectId],
    queryFn: ({ signal }) => fetchProgress(objectId, signal),
  });
}

async function fetchProgress(objectId: string, signal?: AbortSignal): Promise<Progress | null> {
  try {
    return await apiGet<Progress>(`/analysis/objects/${objectId}/progress`, signal);
  } catch (error) {
    if (error instanceof ApiError && error.code === "OBJECT_NOT_ANALYZED") return null;
    throw error;
  }
}

export function useGantt(objectId: string) {
  const plan = useQuery(planQuery(objectId));
  const progress = useQuery(progressQuery(objectId));
  const byStage = new Map((progress.data?.stages ?? []).map((p) => [p.stage_id, p]));
  const rows: GanttRow[] = (plan.data?.stages ?? []).map((stage) => {
    const fact = byStage.get(stage.id) ?? null;
    return {
      stage,
      progress: fact,
      start: dayNumber(stage.plan_start),
      end: dayNumber(stage.plan_end),
      actualStart: fact?.actual_start ? dayNumber(fact.actual_start) : null,
      forecastEnd: fact?.forecast_end ? dayNumber(fact.forecast_end) : null,
    };
  });
  const asOf = progress.data?.as_of ?? null;
  return { plan, progress, rows, asOfDay: asOf ? moscowDay(asOf) : null };
}

/** Все даты, которые должны поместиться в окно диаграммы. */
export function rowDays(rows: GanttRow[], asOfDay: number | null): number[] {
  const days = rows.flatMap((r) => [r.start, r.end, r.actualStart, r.forecastEnd]);
  return [...days, asOfDay].filter((d): d is number => d != null);
}

/** Что показать после правки этапа: прогноз этапа и отставание объекта до и после. */
export type StageSaveResult = {
  before: Snapshot;
  after: Snapshot;
  run: AnalysisSchema<"RunRead">;
};

type Snapshot = {
  stage: StageProgress | null;
  status: ObjectStatus | null;
  critical: boolean | null;
};

export type StageUpdate = PlanSchema<"StageUpdate">;

/**
 * Правка этапа и пересчёт: плановые даты или отметка «этап выполнен» (ADR-0015).
 * plan-service пересчитывает критический путь и сам шлёт анализу сигнал; прогон с ожиданием
 * схлопывается с ним и возвращается, когда прогноз посчитан уже по новому этапу, — как на
 * экране правил.
 */
export function useSaveStage(objectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ stageId, patch }: { stageId: string; patch: StageUpdate }): Promise<StageSaveResult> => {
      const before = await snapshot(objectId, stageId);
      await apiPatch<PlanSchema<"StageRead">>(`/plan/stages/${stageId}`, patch);
      const run = await apiPost<AnalysisSchema<"RunRead">>("/analysis/runs?wait=true", {
        object_id: objectId,
        triggered_by: "MANUAL",
      });
      return { before, after: await snapshot(objectId, stageId), run };
    },
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: ["plan"] }),
        client.invalidateQueries({ queryKey: ["analysis"] }),
      ]),
  });
}

/** Свежие данные мимо кэша: кэш экрана мог устареть от чужой правки. */
async function snapshot(objectId: string, stageId: string): Promise<Snapshot> {
  const [plan, progress, status] = await Promise.all([
    apiGet<Plan>(`/plan/objects/${objectId}/plan`),
    fetchProgress(objectId),
    fetchStatus(objectId),
  ]);
  return {
    stage: progress?.stages.find((s) => s.stage_id === stageId) ?? null,
    status,
    critical: plan.stages.find((s) => s.id === stageId)?.is_critical ?? null,
  };
}

/** Выбранный этап — в адресе (`?stage=`), как на экране правил. */
export function useSelectedRow(rows: GanttRow[]) {
  const [params, setParams] = useSearchParams();
  const selected = rows.find((r) => r.stage.id === params.get("stage")) ?? null;
  const select = (stageId: string | null) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (stageId) next.set("stage", stageId);
        else next.delete("stage");
        return next;
      },
      { replace: true },
    );
  return { selected, select };
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { toBody, type RuleDraft } from "@/features/rules-editor/draft";
import { apiDelete, apiGet, apiPatch, apiPost } from "@/shared/api/client";
import {
  stagesQuery,
  type DeviationRead,
  type RuleRead,
  type StageRead,
} from "@/shared/api/queries";
import type { AnalysisSchema } from "@/shared/api/schemas";

export type RunRead = AnalysisSchema<"RunRead">;

/** Выбранный этап — в адресе (`?stage=`): ссылку на правило можно переслать. */
export function useSelectedStage(objectId: string) {
  const stages = useQuery(stagesQuery(objectId));
  const [params, setParams] = useSearchParams();
  const items = stages.data?.items ?? [];
  const wanted = params.get("stage");
  const stage = items.find((s) => s.id === wanted) ?? items.find((s) => s.rule) ?? items[0] ?? null;
  const select = (next: StageRead) =>
    setParams(
      (prev) => {
        const out = new URLSearchParams(prev);
        out.set("stage", next.id);
        return out;
      },
      { replace: true },
    );
  return { stages, items, stage, select };
}

/**
 * Сохранение правила и пересчёт. plan-service сам шлёт анализу сигнал «пересчитай»; прогон
 * с ожиданием схлопывается с ним и возвращается, когда выводы посчитаны уже по новому
 * правилу. Так лента обновляется без перезагрузки стека (T31).
 */
export function useSaveRule(objectId: string, stage: StageRead) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (draft: RuleDraft): Promise<SaveResult> => {
      const before = await feedCodes(objectId);
      const body = toBody(draft);
      const rule = stage.rule
        ? await apiPatch<RuleRead>(`/plan/rules/${stage.rule.id}`, body)
        : await apiPost<RuleRead>("/plan/rules", { stage_id: stage.id, ...body });
      const run = await apiPost<RunRead>("/analysis/runs?wait=true", {
        object_id: objectId,
        triggered_by: "MANUAL",
      });
      return { rule, run, ...feedDiff(before, await feedCodes(objectId)) };
    },
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: ["plan"] }),
        client.invalidateQueries({ queryKey: ["analysis"] }),
      ]),
  });
}

/**
 * Удаление правила этапа: по нему перестают проверяться D1, D2, D8, D9, прогресс идёт по
 * плану. Как и сохранение — с прогоном анализа и сравнением ленты до и после.
 */
export function useDeleteRule(objectId: string, stage: StageRead) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      if (!stage.rule) throw new Error("У этапа нет правила");
      const before = await feedCodes(objectId);
      await apiDelete(`/plan/rules/${stage.rule.id}`);
      await apiPost<RunRead>("/analysis/runs?wait=true", { object_id: objectId, triggered_by: "MANUAL" });
      return feedDiff(before, await feedCodes(objectId));
    },
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: ["plan"] }),
        client.invalidateQueries({ queryKey: ["analysis"] }),
      ]),
  });
}

export type SaveResult = {
  rule: RuleRead;
  run: RunRead;
  /** Строки ленты, которых после пересчёта нет / которые появились: `D2 — Неполный комплект…`. */
  gone: DeviationRead[];
  added: DeviationRead[];
};

/**
 * Лента до и после — по id строки. Статистика одного прогона тут не годится: plan-service
 * мог пересчитать объект по своему сигналу раньше, и наш прогон уже ничего не поменял бы.
 */
async function feedCodes(objectId: string): Promise<DeviationRead[]> {
  const page = await apiGet<AnalysisSchema<"Page_DeviationRead_">>(
    `/analysis/deviations?object_id=${objectId}&limit=200`,
  );
  return page.items;
}

function feedDiff(before: DeviationRead[], after: DeviationRead[]) {
  const ids = (items: DeviationRead[]) => new Set(items.map((d) => d.id));
  const was = ids(before);
  const now = ids(after);
  return {
    gone: before.filter((d) => !now.has(d.id)),
    added: after.filter((d) => !was.has(d.id)),
  };
}

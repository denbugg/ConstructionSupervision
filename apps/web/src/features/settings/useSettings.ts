import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPatch } from "@/shared/api/client";
import type { AnalysisSchema, PlanSchema } from "@/shared/api/schemas";

export type DeviationRule = AnalysisSchema<"DeviationRuleRead">;
export type EquipmentClass = PlanSchema<"EquipmentClassRead">;

/** Настройки D1–D10: общие для всех объектов, действуют со следующего прогона. */
export const deviationRulesQuery = queryOptions({
  queryKey: ["analysis", "deviation-rules"],
  queryFn: ({ signal }) =>
    apiGet<AnalysisSchema<"Page_DeviationRuleRead_">>("/analysis/deviation-rules?limit=50", signal),
});

export function useDeviationRules() {
  return useQuery(deviationRulesQuery);
}

export function useUpdateDeviationRule(code: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: AnalysisSchema<"DeviationRuleUpdate">) =>
      apiPatch<DeviationRule>(`/analysis/deviation-rules/${code}`, body),
    onSuccess: () => client.invalidateQueries({ queryKey: deviationRulesQuery.queryKey }),
  });
}

/** Классы техники целиком — тот же ключ кэша, что у словаря названий. */
export function useEquipmentClasses() {
  return useQuery({
    queryKey: ["plan", "equipment-classes"],
    queryFn: ({ signal }) =>
      apiGet<PlanSchema<"Page_EquipmentClassRead_">>("/plan/equipment-classes?limit=200", signal),
    staleTime: Infinity,
  });
}

/** Скалярные параметры правила — то, что правится полем; словари (тексты вариантов) — нет. */
export function scalarParams(params: Record<string, unknown>): [string, number | string | boolean][] {
  return Object.entries(params).flatMap(([key, value]) =>
    typeof value === "number" || typeof value === "string" || typeof value === "boolean"
      ? [[key, value] as [string, number | string | boolean]]
      : [],
  );
}

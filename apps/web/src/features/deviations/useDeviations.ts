import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { apiPatch } from "@/shared/api/client";
import {
  deviationsQuery,
  explainQuery,
  type DeviationFilter,
  type DeviationRead,
} from "@/shared/api/queries";

/**
 * Пресеты статуса в фильтре: оператору нужны «что открыто» и «что было», а не четыре флажка.
 * «Ложные» — по вердикту, а не по статусу: закрытое, помеченное ложным, остаётся `RESOLVED`.
 */
export const STATUS_PRESETS = {
  all: { label: "Все", statuses: [], verdicts: [] },
  open: { label: "Открытые", statuses: ["NEW", "CONFIRMED"], verdicts: [] },
  resolved: { label: "Закрытые", statuses: ["RESOLVED"], verdicts: [] },
  rejected: { label: "Ложные", statuses: [], verdicts: ["REJECTED"] },
} as const satisfies Record<string, { label: string; statuses: string[]; verdicts: string[] }>;

export type StatusPreset = keyof typeof STATUS_PRESETS;

const isPreset = (value: string | null): value is StatusPreset =>
  value != null && value in STATUS_PRESETS;

/**
 * Фильтры и выбранное отклонение живут в адресе (`?code=&severity=&status=&from=&to=&id=`):
 * ссылку на карточку можно переслать, а «назад» в браузере возвращает прежний фильтр.
 * Без `status` лента показывает открытые: оператор приходит разбирать то, что ждёт решения.
 */
export const DEFAULT_PRESET: StatusPreset = "open";

export function useDeviationFilter() {
  const [params, setParams] = useSearchParams();
  const preset: StatusPreset = isPreset(params.get("status")) ? (params.get("status") as StatusPreset) : DEFAULT_PRESET;
  const filter: DeviationFilter = {
    codes: params.get("code") ? [params.get("code")!] : [],
    severities: params.get("severity") ? [params.get("severity")!] : [],
    statuses: [...STATUS_PRESETS[preset].statuses],
    verdicts: [...STATUS_PRESETS[preset].verdicts],
    from: params.get("from"),
    to: params.get("to"),
  };
  const update = (changes: Record<string, string | null>) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(changes)) {
          if (value) next.set(key, value);
          else next.delete(key);
        }
        return next;
      },
      { replace: true },
    );
  return { filter, preset, selectedId: params.get("id"), update };
}

export function useDeviations(objectId: string, filter: DeviationFilter, selectedId: string | null) {
  const feed = useQuery(deviationsQuery(objectId, filter));
  const items = feed.data?.items ?? [];
  // Без выбора — первая карточка ленты: пустая правая половина экрана ничего не объясняет.
  const selected = items.find((d) => d.id === selectedId) ?? items[0] ?? null;
  return { feed, items, selected };
}

/**
 * Соседняя карточка ленты: для листания стрелками и перехода к следующей после вердикта.
 * На краю ленты — `null`.
 */
export function neighbour(items: DeviationRead[], current: DeviationRead | null, step: 1 | -1): DeviationRead | null {
  if (!current) return items[0] ?? null;
  const index = items.findIndex((d) => d.id === current.id);
  return items[index + step] ?? null;
}

export function useExplain(deviationId: string) {
  return useQuery(explainQuery(deviationId));
}

/** Вердикт оператора; после него обновляются лента, карточка и счётчики дашборда. */
export function useVerdict(deviation: DeviationRead) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (verdict: { status: "CONFIRMED" | "REJECTED"; comment: string }) =>
      apiPatch<DeviationRead>(`/analysis/deviations/${deviation.id}`, {
        status: verdict.status,
        comment: verdict.comment.trim() || null,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["analysis"] }),
  });
}

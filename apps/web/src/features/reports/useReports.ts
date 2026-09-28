import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { moscowIsoDay, shiftIsoDay } from "@/entities/format";
import { apiGet, apiPost } from "@/shared/api/client";
import { deviationsQuery, objectQuery, statusQuery, type DeviationFilter } from "@/shared/api/queries";
import type { AnalysisSchema } from "@/shared/api/schemas";

export type ReportRead = AnalysisSchema<"ReportRead">;
export type ReportCreated = AnalysisSchema<"ReportCreated">;

/** Период отчёта — местные дни включительно, `YYYY-MM-DD`. */
export type Period = { from: string; to: string };

// Столько же дней, сколько REPORT_DEFAULT_DAYS у analysis: форма показывает, что сервис
// взял бы и без неё.
const DEFAULT_DAYS = 7;

/**
 * Период по умолчанию: неделя по день момента анализа. Отчёт оформляет посчитанные выводы,
 * поэтому «сегодня» здесь ни при чём — демо-хронология датирована графиком (октябрь 2026).
 */
export function defaultPeriod(asOf: string, days = DEFAULT_DAYS): Period {
  const to = moscowIsoDay(asOf);
  return { from: shiftIsoDay(to, -(days - 1)), to };
}

/** Быстрые периоды формы: сколько дней по день момента анализа. */
export const PERIOD_PRESETS = [
  { label: "Неделя", days: DEFAULT_DAYS },
  { label: "2 недели", days: 14 },
  { label: "Месяц", days: 30 },
] as const;

/** Почему период нельзя отправить; `null` — можно. */
export function periodProblem(period: Period): string | null {
  if (!period.from || !period.to) return "Укажите обе даты периода.";
  if (period.from > period.to) return "Начало периода позже конца.";
  return null;
}

/**
 * Отчёты объекта, новые сверху. Presigned-ссылки живут час (`S3_PRESIGN_TTL_S`), поэтому
 * список считается устаревшим через пять минут и перечитывается при возврате на вкладку.
 */
export function reportsQuery(objectId: string) {
  return queryOptions({
    queryKey: ["analysis", "reports", objectId],
    queryFn: ({ signal }) =>
      apiGet<AnalysisSchema<"Page_ReportRead_">>(
        `/analysis/reports?object_id=${objectId}&limit=200`,
        signal,
      ),
    staleTime: 5 * 60 * 1000,
  });
}

export function useReports(objectId: string) {
  const object = useQuery(objectQuery(objectId));
  const status = useQuery(statusQuery(objectId));
  const reports = useQuery(reportsQuery(objectId));
  return { object, status, reports };
}

/**
 * Резюме за период без PDF: тот же контекст, что у отчёта. Текст нейросети проходит сверку
 * чисел с фактами, иначе резюме шаблонное — источник показывается всегда (ADR-0008).
 */
export function useSummary(objectId: string) {
  return useMutation({
    mutationFn: (period: Period) =>
      apiPost<AnalysisSchema<"SummaryRead">>("/analysis/summary", {
        object_id: objectId,
        period_from: period.from,
        period_to: period.to,
      }),
  });
}

const ALL_DEVIATIONS: DeviationFilter = {
  codes: [],
  severities: [],
  statuses: [],
  verdicts: [],
  from: null,
  to: null,
};

/**
 * Полный ID отклонения по первым восьми знакам — так на отклонения ссылается резюме. Лента —
 * одна страница в 200 строк: ссылка на более старое останется текстом.
 */
export function useDeviationRefs(objectId: string): Map<string, string> {
  const feed = useQuery(deviationsQuery(objectId, ALL_DEVIATIONS));
  return new Map((feed.data?.items ?? []).map((d) => [d.id.slice(0, 8), d.id]));
}

/** Формирование PDF: синхронный ответ с готовой ссылкой, затем свежий список. */
export function useCreateReport(objectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (period: Period) =>
      apiPost<ReportCreated>("/analysis/reports", {
        object_id: objectId,
        period_from: period.from,
        period_to: period.to,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["analysis", "reports", objectId] }),
  });
}

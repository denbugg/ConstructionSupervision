/**
 * Запросы, которые нужны нескольким экранам. Ключи кэша — `[сервис, ресурс, …]`: после
 * пересчёта достаточно сбросить всё, что начинается с `["analysis"]`.
 */
import { queryOptions } from "@tanstack/react-query";

import { ApiError, apiGet } from "@/shared/api/client";
import type { AnalysisSchema, PlanSchema, SiteSchema } from "@/shared/api/schemas";

/** Фильтры ленты отклонений; пустой список — без фильтра по этому полю. */
export type DeviationFilter = {
  codes: string[];
  severities: string[];
  statuses: string[];
  /** Вердикт оператора: у закрытого он в поле `verdict`, статус остаётся `RESOLVED`. */
  verdicts: string[];
  /** Сутки по Москве, `YYYY-MM-DD`: эпизоды, пересекающиеся с [from, to]. */
  from: string | null;
  to: string | null;
};

export type ObjectRead = PlanSchema<"ObjectRead">;
export type ObjectStatus = AnalysisSchema<"ObjectStatusRead">;
export type CameraRead = SiteSchema<"CameraRead">;
export type ZoneRead = SiteSchema<"ZoneRead">;
export type ImageRead = SiteSchema<"ImageRead">;
export type ImageDetail = SiteSchema<"ImageDetail">;
export type DeviationRead = AnalysisSchema<"DeviationRead">;
export type StageRead = PlanSchema<"StageRead">;
export type RuleRead = PlanSchema<"RuleRead">;
export type ExplainRead = AnalysisSchema<"ExplainRead">;

// Камер и зон у объекта единицы, снимков в демо — десятки: одной страницы в 200 хватает.
// Больше 200 снимков у камеры — экран покажет последние 200 и скажет об этом.
const PAGE = 200;

/** Камеры объекта, включая выключенные: на экране они видны, но помечены. */
export function camerasQuery(objectId: string) {
  return queryOptions({
    queryKey: ["site", "cameras", objectId],
    queryFn: ({ signal }) =>
      apiGet<SiteSchema<"Page_CameraRead_">>(
        `/site/cameras?object_id=${objectId}&limit=${PAGE}`,
        signal,
      ),
  });
}

/** Активные зоны одной камеры. */
export function zonesQuery(cameraId: string) {
  return queryOptions({
    queryKey: ["site", "zones", cameraId],
    queryFn: ({ signal }) =>
      apiGet<SiteSchema<"Page_ZoneRead_">>(`/site/zones?camera_id=${cameraId}&limit=${PAGE}`, signal),
  });
}

/** Участки объекта: какие подписи уже есть — чтобы связать зоны разных камер одним участком. */
export function areasQuery(objectId: string) {
  return queryOptions({
    queryKey: ["site", "areas", objectId],
    queryFn: ({ signal }) =>
      apiGet<SiteSchema<"ObjectAreas">>(`/site/objects/${objectId}/areas`, signal),
  });
}

/**
 * Сколько снимков объекта в статусе — `total` страницы из одного элемента. Нужен счётчикам:
 * очередь распознавания, снимки без времени.
 */
export function imageCountQuery(objectId: string, status?: string) {
  const filter = status ? `&status=${status}` : "";
  return queryOptions({
    queryKey: ["site", "images", objectId, "count", status ?? "ALL"],
    queryFn: ({ signal }) =>
      apiGet<SiteSchema<"Page_ImageRead_">>(
        `/site/images?object_id=${objectId}${filter}&limit=1`,
        signal,
      ),
    select: (page) => page.total,
  });
}

/** Карточка снимка: presigned-ссылка, размер кадра, рамки детекций. */
export function imageQuery(imageId: string) {
  return queryOptions({
    queryKey: ["site", "image", imageId],
    queryFn: ({ signal }) => apiGet<ImageDetail>(`/site/images/${imageId}`, signal),
  });
}

/** Русские названия классов техники из plan: в коде интерфейса классов нет (CONTRIBUTING.md, §2). */
export const equipmentClassesQuery = queryOptions({
  queryKey: ["plan", "equipment-classes"],
  queryFn: ({ signal }) =>
    apiGet<PlanSchema<"Page_EquipmentClassRead_">>(`/plan/equipment-classes?limit=${PAGE}`, signal),
  select: (page) => new Map(page.items.map((c) => [c.code, c.name_ru])),
  staleTime: Infinity,
});

export const objectsQuery = queryOptions({
  queryKey: ["plan", "objects"],
  // Объектов на демо-стенде единицы: одной страницы в 200 хватает с запасом.
  queryFn: ({ signal }) => apiGet<PlanSchema<"Page_ObjectRead_">>("/plan/objects?limit=200", signal),
});

/** Этапы объекта по `seq` вместе с правилами «этап → техника». */
export function stagesQuery(objectId: string) {
  return queryOptions({
    queryKey: ["plan", "stages", objectId],
    queryFn: ({ signal }) =>
      apiGet<PlanSchema<"Page_StageRead_">>(`/plan/objects/${objectId}/stages?limit=${PAGE}`, signal),
  });
}

export function objectQuery(objectId: string) {
  return queryOptions({
    queryKey: ["plan", "objects", objectId],
    queryFn: ({ signal }) => apiGet<ObjectRead>(`/plan/objects/${objectId}`, signal),
  });
}

// Москва — UTC+3 без перехода на летнее время: сутки фильтра — от полуночи по Москве.
const MOSCOW_OFFSET = "+03:00";

/** Лента отклонений объекта; новые сверху (сортировка API по умолчанию — по `last_seen_at`). */
export function deviationsQuery(objectId: string, filter: DeviationFilter) {
  const params = new URLSearchParams({ object_id: objectId, limit: String(PAGE) });
  filter.codes.forEach((c) => params.append("code", c));
  filter.severities.forEach((s) => params.append("severity", s));
  filter.statuses.forEach((s) => params.append("status", s));
  filter.verdicts.forEach((v) => params.append("verdict", v));
  if (filter.from) params.set("from", `${filter.from}T00:00:00${MOSCOW_OFFSET}`);
  if (filter.to) params.set("to", `${nextDay(filter.to)}T00:00:00${MOSCOW_OFFSET}`);
  return queryOptions({
    queryKey: ["analysis", "deviations", objectId, filter],
    queryFn: ({ signal }) =>
      apiGet<AnalysisSchema<"Page_DeviationRead_">>(`/analysis/deviations?${params}`, signal),
  });
}

/** Полное объяснение: настройка правила, проверенные сессии с фактами участка, снимки. */
export function explainQuery(deviationId: string) {
  return queryOptions({
    queryKey: ["analysis", "explain", deviationId],
    queryFn: ({ signal }) =>
      apiGet<ExplainRead>(`/analysis/deviations/${deviationId}/explain`, signal),
  });
}

function nextDay(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

/**
 * Статус объекта; `null` — прогона ещё не было (`OBJECT_NOT_ANALYZED`). Это не ошибка, а
 * состояние объекта: экран объясняет его словами, а не красной плашкой.
 */
export function statusQuery(objectId: string) {
  return queryOptions({
    queryKey: ["analysis", "status", objectId],
    queryFn: ({ signal }) => fetchStatus(objectId, signal),
  });
}

export async function fetchStatus(objectId: string, signal?: AbortSignal): Promise<ObjectStatus | null> {
  try {
    return await apiGet<ObjectStatus>(`/analysis/objects/${objectId}/status`, signal);
  } catch (error) {
    if (error instanceof ApiError && error.code === "OBJECT_NOT_ANALYZED") return null;
    throw error;
  }
}

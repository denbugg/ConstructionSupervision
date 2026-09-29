/**
 * Форма объекта: черновик полей, проверка и тело запроса. Чистые функции: экран только
 * показывает поля и ошибки, отсюда же берутся тела `POST` и `PATCH /plan/objects`.
 */
import type { ObjectRead } from "@/shared/api/queries";
import type { PlanSchema } from "@/shared/api/schemas";

export type ObjectType = ObjectRead["object_type"];
export type Lifecycle = ObjectRead["status"];

/** Поля формы — строками, как в полях ввода: число проверяется при отправке. */
export type ObjectDraft = {
  name: string;
  address: string;
  objectType: ObjectType;
  planStart: string;
  status: Lifecycle;
  tep: TepDraft;
};

/**
 * Параметры генератора графика (МРР-3.2.81-12): этажность и площадь обязательны для
 * генерации, остальное plan-service берёт по умолчанию. Ключи — как в `tep` объекта.
 */
export type TepDraft = { floors: string; total_area: string; sections: string; piles: string; shifts: string };
export const TEP_KEYS = ["floors", "total_area", "sections", "piles", "shifts"] as const;

const DEFAULT_TYPE: ObjectType = "RESIDENTIAL_MONOLITH";

/**
 * Типы, для которых plan-service умеет строить график по МРР: нормы есть только для
 * монолитного жилого дома (services/plan-service/data/mrr_norms.json). Для остальных
 * генерация (`POST /objects/{id}/plan/generate`) отвечает NORMS_NOT_AVAILABLE — график только из файла.
 * API перечня не отдаёт, поэтому список повторён здесь; появятся нормы — дополнить.
 */
const GENERATOR_TYPES: readonly ObjectType[] = ["RESIDENTIAL_MONOLITH"];

export function hasGenerator(type: ObjectType): boolean {
  return GENERATOR_TYPES.includes(type);
}

/** Подпись там, где расчёт по МРР недоступен: вместо кнопки, которая заведомо упадёт. */
export const NO_GENERATOR_NOTE =
  "Автоматический расчёт графика — только для монолитного жилого дома. Для этого типа загрузите график из файла.";

export function draftFromObject(object?: ObjectRead): ObjectDraft {
  return {
    name: object?.name ?? "",
    address: object?.address ?? "",
    objectType: object?.object_type ?? DEFAULT_TYPE,
    planStart: object?.plan_start ?? "",
    status: object?.status ?? "DRAFT",
    tep: tepDraft(object?.tep),
  };
}

export function tepDraft(tep: Record<string, unknown> | undefined): TepDraft {
  const read = (key: string) => {
    const value = tep?.[key];
    return typeof value === "number" || typeof value === "string" ? String(value) : "";
  };
  return {
    floors: read("floors"),
    total_area: read("total_area"),
    sections: read("sections"),
    piles: read("piles"),
    shifts: read("shifts"),
  };
}

/** «10 000», «1,5» → число; пусто — `null`; не число — `NaN`. */
export function parseNumber(value: string): number | null {
  const clean = value.replace(/\s/g, "").replace(",", ".");
  if (clean === "") return null;
  return Number(clean);
}

export type DraftProblems = Partial<Record<"name" | "planStart" | keyof TepDraft, string>>;

/**
 * Что мешает отправить форму. `forGenerator` — график будут строить по нормам: тогда нужны
 * дата начала, этажность и площадь (без них plan-service ответит GENERATOR_PARAMS_INVALID).
 * У типа без генератора поля ТЭП скрыты — их не проверяем, иначе невидимая ошибка держала бы форму.
 */
export function draftProblems(draft: ObjectDraft, forGenerator: boolean): DraftProblems {
  const problems: DraftProblems = {};
  if (!draft.name.trim()) problems.name = "Укажите название объекта";
  if (forGenerator && !draft.planStart) problems.planStart = "Нужна для расчёта дат этапов";
  if (!hasGenerator(draft.objectType)) return problems;
  for (const key of TEP_KEYS) {
    const value = parseNumber(draft.tep[key]);
    if (value != null && (Number.isNaN(value) || value < 0)) problems[key] = "Нужно число не меньше нуля";
  }
  if (forGenerator) {
    if (parseNumber(draft.tep.floors) == null) problems.floors = "Нужна для генерации графика";
    if (parseNumber(draft.tep.total_area) == null) problems.total_area = "Нужна для генерации графика";
  }
  return problems;
}

/**
 * `tep` для отправки: прежние ключи объекта сохраняются, пять ключей генератора берутся из
 * формы. Пустое поле убирает ключ — тогда генератор возьмёт значение по умолчанию.
 */
export function tepBody(draft: TepDraft, base: Record<string, unknown> = {}): Record<string, unknown> {
  const tep: Record<string, unknown> = { ...base };
  for (const key of TEP_KEYS) {
    const value = parseNumber(draft[key]);
    if (value == null || Number.isNaN(value)) delete tep[key];
    else tep[key] = value;
  }
  return tep;
}

export function createBody(draft: ObjectDraft): PlanSchema<"ObjectCreate"> {
  return {
    name: draft.name.trim(),
    address: draft.address.trim() || null,
    object_type: draft.objectType,
    plan_start: draft.planStart || null,
    // В схеме `tep` — словарь без описания значений: числа кладутся как есть. Скрытые для
    // этого типа поля не отправляем: этажность дороги ничего не значит и никем не читается.
    tep: (hasGenerator(draft.objectType) ? tepBody(draft.tep) : {}) as PlanSchema<"ObjectCreate">["tep"],
  };
}

/**
 * Тело PATCH — только изменённые поля. Иначе неизменённая дата начала ушла бы в запрос, а у
 * объекта с графиком plan-service её напрямую не меняет: только перестройкой графика.
 */
export function updateBody(draft: ObjectDraft, object: ObjectRead): PlanSchema<"ObjectUpdate"> {
  const body: PlanSchema<"ObjectUpdate"> = {};
  const name = draft.name.trim();
  const address = draft.address.trim() || null;
  const planStart = draft.planStart || null;
  const base = object.tep as Record<string, unknown>;
  // Тип без генератора: поля ТЭП скрыты, прежние значения объекта не трогаем — вернут тип, вернутся и они.
  const tep = hasGenerator(draft.objectType) ? tepBody(draft.tep, base) : base;
  if (name !== object.name) body.name = name;
  if (address !== object.address) body.address = address;
  if (draft.objectType !== object.object_type) body.object_type = draft.objectType;
  if (planStart !== object.plan_start) body.plan_start = planStart;
  if (draft.status !== object.status) body.status = draft.status;
  if (JSON.stringify(tep) !== JSON.stringify(object.tep)) body.tep = tep as PlanSchema<"ObjectUpdate">["tep"];
  return body;
}

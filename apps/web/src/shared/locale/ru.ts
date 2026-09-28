/**
 * Общие русские строки интерфейса: названия перечислений, состояния экранов, единицы.
 * Строки конкретного экрана пишутся прямо в JSX (apps/web/README.md, §5). Названия значений
 * перечислений повторяют enums.yaml: новое значение без строки здесь покажется как есть.
 */
import type { PlanSchema, SiteSchema } from "@/shared/api/schemas";

export type ZoneType = SiteSchema<"ZoneCreate">["zone_type"];
export type StageLabel = NonNullable<PlanSchema<"Signature">["stage_label"]>;

export const ru = {
  app: {
    title: "СтройКонтроль",
    subtitle: "Мониторинг строительной площадки по снимкам камер",
  },
  nav: {
    objects: "Объекты",
  },
  states: {
    loading: "Загружаем данные…",
    empty: "Данных пока нет",
    error: "Не удалось загрузить данные",
    requestId: "Идентификатор запроса",
    retry: "Повторить",
  },
  notFound: {
    title: "Страница не найдена",
    hint: "Проверьте адрес или вернитесь к списку объектов.",
  },
  units: {
    workDays: "раб. дн.",
  },
  objectType: {
    RESIDENTIAL_MONOLITH: "Жилой монолитный дом",
    RESIDENTIAL_PANEL: "Жилой панельный дом",
    PUBLIC_BUILDING: "Общественное здание",
    ROAD: "Дорога",
  } as Record<string, string>,
  objectLifecycle: {
    DRAFT: "Черновик",
    ACTIVE: "В работе",
    ARCHIVED: "В архиве",
  } as Record<string, string>,
  objectStatus: {
    ON_TRACK: "В графике",
    DELAY: "Отставание",
    AHEAD: "Опережение",
    UNKNOWN: "Недостаточно данных",
  } as Record<string, string>,
  confidence: {
    LOW: "низкая",
    MEDIUM: "средняя",
    HIGH: "высокая",
  } as Record<string, string>,
  severity: {
    HIGH: "Высокая",
    MEDIUM: "Средняя",
    LOW: "Низкая",
    INFO: "Инфо",
  } as Record<string, string>,
  stageFactStatus: {
    NOT_STARTED: "не начаты",
    IN_PROGRESS: "в работе",
    DONE: "завершены",
    LATE: "с опозданием",
    AHEAD: "с опережением",
  } as Record<string, string>,
  // Статус одного этапа (карточка этапа на Ганте); выше — те же значения во множественном числе.
  stageStatus: {
    NOT_STARTED: "Не начат",
    IN_PROGRESS: "В работе",
    DONE: "Завершён",
    LATE: "С опозданием",
    AHEAD: "С опережением",
  } as Record<string, string>,
  // Типы связей этапов (interservice.md, §1): что с чем связано.
  linkType: {
    FS: "окончание → начало",
    SS: "начало → начало",
    FF: "окончание → окончание",
    SF: "начало → окончание",
  } as Record<string, string>,
  // enums.yaml: zone_type_name. `satisfies` ловит новый тип зоны в контракте на сборке.
  zoneType: {
    PIT: "Котлован",
    BUILDING_FOOTPRINT: "Пятно застройки",
    PERIMETER: "Периметр",
    ENTRY_GATE: "Въезд",
    STORAGE: "Склад",
    DANGER: "Опасная зона",
    ROAD: "Дорога",
  } satisfies Record<ZoneType, string>,
  // enums.yaml: zone_type_role — что значит машина на участке этого типа (methodology.md, §6).
  zoneRole: {
    PIT: "рабочий: техника здесь работает",
    BUILDING_FOOTPRINT: "рабочий: техника здесь работает",
    PERIMETER: "рабочий: техника здесь работает",
    ROAD: "рабочий: техника здесь работает",
    ENTRY_GATE: "служебный: стоящая здесь техника простаивает",
    STORAGE: "служебный: стоящая здесь техника простаивает",
    DANGER: "опасная зона: техника и люди здесь — нарушение",
  } satisfies Record<ZoneType, string>,
  // docs/methodology.md, раздел 9: коды отклонений и их короткие названия.
  deviationCode: {
    D1: "Нет обязательной техники",
    D2: "Неполный комплект",
    D3: "Техника не по этапу",
    D4: "Простой",
    D5: "Не та зона",
    D6: "Опасная зона",
    D7: "Стадия не совпадает",
    D8: "Этап затянулся",
    D9: "Не начат в срок",
    D10: "Вне контроля ИИ",
  } as Record<string, string>,
  deviationStatus: {
    NEW: "Новое",
    CONFIRMED: "Подтверждено",
    REJECTED: "Ложное",
    RESOLVED: "Закрыто",
  } as Record<string, string>,
  // enums.yaml: stage_label — стадия объекта по снимку (methodology.md, раздел 8).
  stageLabel: {
    PIT: "Котлован",
    PILES: "Сваи",
    FOUNDATION: "Фундамент",
    FRAME: "Каркас",
    FACADE: "Фасад",
    LANDSCAPING: "Благоустройство",
  } satisfies Record<StageLabel, string>,
  verdict: {
    CONFIRMED: "Подтверждено оператором",
    REJECTED: "Ложное срабатывание",
  } as Record<string, string>,
  // Источник резюме отчёта (ADR-0008): показывается всегда, рядом с самим текстом.
  summarySource: {
    TEMPLATE: "шаблон по фактам, без нейросети",
    LLM: "нейросеть, все числа сверены с фактами",
  } as Record<string, string>,
  visibility: {
    OK: "виден",
    PARTIAL: "виден частично",
    BLIND: "не виден",
  } as Record<string, string>,
  imageStatus: {
    PENDING: "ждёт распознавания",
    PROCESSING: "распознаётся",
    ANALYZED: "распознан",
    FAILED: "ошибка распознавания",
    NEEDS_TIME: "нет времени съёмки",
  } as Record<string, string>,
  // Параметры правил D1–D10 (methodology.md, раздел 9): неизвестный ключ покажется как есть.
  ruleParam: {
    min_sessions: "Сессий подряд",
    escalate_after_days: "Повысить через, раб. дн.",
    escalate_to: "Повысить до",
    k_days: "Допуск K, раб. дн.",
    min_visible_share: "Мин. доля видимости",
  } as Record<string, string>,
  // enums.yaml: equipment_group — группа класса техники.
  equipmentGroup: {
    EARTHWORKS: "Земляные работы",
    LIFTING: "Подъём",
    CONCRETE: "Бетон",
    TRANSPORT: "Транспорт",
    ROAD: "Дорожные работы",
    OTHER: "Прочее",
  } as Record<string, string>,
  // Фаза этапа (enums.yaml: construction_phase).
  stagePhase: {
    PREPARATORY: "Подготовка",
    SUBSTRUCTURE: "Подземная часть",
    SUPERSTRUCTURE: "Надземная часть",
    ENVELOPE_ROOF: "Фасад и кровля",
    NETWORKS: "Сети",
    LANDSCAPING: "Благоустройство",
  } as Record<string, string>,
} as const;

/** Название значения перечисления; неизвестное значение показывается как есть, а не пропадает. */
export function label(names: Record<string, string>, value: string | null | undefined): string {
  if (value == null) return "—";
  return names[value] ?? value;
}

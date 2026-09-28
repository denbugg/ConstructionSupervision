/**
 * Разбор отклонения для экрана: числа из `facts` и строки проверенных сессий из `/explain`.
 *
 * `facts` и сессии приходят объектами без схемы (их состав зависит от кода отклонения,
 * docs/methodology.md, раздел 12), поэтому каждое поле читается с проверкой типа:
 * неизвестная форма даёт прочерк, а не падение экрана.
 */
import { formatMoment, formatPlanDate } from "@/entities/format";
import { label, ru } from "@/shared/locale/ru";

type Facts = Record<string, unknown>;
type Names = (code: string) => string;

const text = (v: unknown) => (typeof v === "string" ? v : null);
const number = (v: unknown) => (typeof v === "number" ? v : null);
const record = (v: unknown): Facts | null =>
  v != null && typeof v === "object" && !Array.isArray(v) ? (v as Facts) : null;
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

/** Группа правила этапа: «любой из» классов, норма и сколько наблюдалось. */
export type GroupRow = { classes: string; min: number; observed: number; ok: boolean };

/** Группы `required` с наблюдением (D1, D2): из них видно, чего именно не хватило. */
export function groupRows(facts: Facts, names: Names): GroupRow[] {
  return list(facts.groups).flatMap((item) => {
    const group = record(item);
    const min = number(group?.min);
    const observed = number(group?.observed);
    if (!group || min == null || observed == null) return [];
    const classes = list(group.any_of)
      .map((c) => (typeof c === "string" ? names(c) : "?"))
      .join(" или ");
    return [{ classes, min, observed, ok: observed >= min }];
  });
}

export type FactLine = { label: string; value: string };

/**
 * Ключевые числа вывода в том порядке, в каком их читает оператор: этап и его даты, машина
 * и её статус, почему участок не виден, сколько держалось. Отсутствующие поля пропускаются.
 */
export function factLines(facts: Facts): FactLine[] {
  const lines: FactLine[] = [];
  const add = (name: string, value: string | null) => {
    if (value != null && value !== "") lines.push({ label: name, value });
  };
  const stage = text(facts.stage_name);
  if (stage) {
    add("Этап", `${text(facts.stage_code) ?? ""} ${stage}`.trim());
    const start = text(facts.plan_start);
    const end = text(facts.plan_end);
    if (start || end) add("По плану", `${formatPlanDate(start)} — ${formatPlanDate(end)}`);
  }
  add("Участок", text(facts.area_name));
  const equipment = text(facts.equipment_name);
  if (equipment) {
    const count = number(facts.count);
    const still = number(facts.static);
    add(
      "Техника",
      `${equipment}${count != null ? `, ${count} ед.` : ""}${
        still != null ? `, неподвижны ${still}` : ""
      }`,
    );
  }
  add("Почему так", text(facts.state_reason));
  const active = list(facts.active_stages).filter((s): s is string => typeof s === "string");
  if (active.length) add("Активные этапы", active.join(", "));
  const expected = list(facts.expected_classes).filter((s): s is string => typeof s === "string");
  if (expected.length) add("Ожидается на участке", expected.join(", "));
  const future = text(facts.future_stage_name);
  if (future) add("Есть в правиле будущего этапа", `${future} с ${formatPlanDate(text(facts.future_plan_start))}`);
  const reason = text(facts.reason_name);
  if (reason) {
    const usable = number(facts.cameras_usable);
    const total = number(facts.cameras_total);
    add("Причина", `${reason}${usable != null && total != null ? `, камер пригодно ${usable} из ${total}` : ""}`);
  }
  add("Доказательства", text(facts.evidence_absent_reason));
  const checked = number(facts.sessions_checked);
  if (checked != null) add("Сессий подряд", String(checked));
  const window = number(facts.transient_window_sessions);
  if (window != null) add("Окно транзитной техники", `${window} сессии`);
  const held = number(facts.held_working_days);
  if (held != null && held > 0) add("Держится", `${held} ${ru.units.workDays}`);
  return lines;
}

/** Кусок текста резюме: обычный текст или ссылка на отклонение по первым восьми знакам ID. */
export type SummaryPart = { text: string; ref: boolean };

// Как ссылается резюме analysis-service (report/summary.py, DEVIATION_REF): восемь hex-знаков.
const DEVIATION_REF = /\b([0-9a-f]{8})\b/;

/** Резюме на куски: ссылки на отклонения отдельно, чтобы экран сделал их ссылками. */
export function splitRefs(text: string): SummaryPart[] {
  // split с группой кладёт найденное на нечётные места.
  return text
    .split(DEVIATION_REF)
    .map((part, i) => ({ text: part, ref: i % 2 === 1 }))
    .filter((part) => part.text !== "");
}

/** Строка таблицы проверенных сессий: время, видимость участка, техника на нём. */
export type SessionRow = {
  id: string;
  at: string;
  visibility: string;
  equipment: string;
};

/**
 * Сессии эпизода из `/explain`, только по участку отклонения. Люди в перечне техники не
 * показываются: их на обзорной камере десятки, а к выводу они отношения не имеют (D6 — отдельно).
 */
export function sessionRows(sessions: unknown[], area: string | null, names: Names): SessionRow[] {
  return sessions.flatMap((item, index) => {
    const session = record(item);
    if (!session) return [];
    const at = formatMoment(text(session.window_start));
    const place = list(session.areas)
      .map(record)
      .find((a) => a != null && a.area === area);
    if (!place) {
      return [{ id: String(index), at, visibility: "участка нет в фактах", equipment: "—" }];
    }
    const seen = record(place.visibility);
    const usable = number(seen?.cameras_usable);
    const total = number(seen?.cameras_total);
    const visibility = `${label(ru.visibility, text(seen?.status))}${
      usable != null && total != null ? ` (${usable} из ${total})` : ""
    }`;
    const equipment =
      list(place.equipment)
        .map(record)
        .flatMap((e) => {
          const code = text(e?.equipment_class);
          const count = number(e?.count);
          if (!code || code === "person" || count == null) return [];
          const still = number(e?.static);
          return [`${names(code)} ${count}${still ? `, стоят ${still}` : ""}`];
        })
        .join("; ") || "техники нет";
    return [{ id: text(session.session_id) ?? String(index), at, visibility, equipment }];
  });
}

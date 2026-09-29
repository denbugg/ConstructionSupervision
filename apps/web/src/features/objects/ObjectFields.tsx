import type { DraftProblems, ObjectDraft, ObjectType, TepDraft } from "@/features/objects/objectDraft";
import { ru } from "@/shared/locale/ru";
import { Field, inputClass, selectClass } from "@/shared/ui/Field";

const OBJECT_TYPES = Object.keys(ru.objectType) as ObjectType[];

/** Реквизиты объекта: название, тип, адрес, начало СМР. */
export function RequisiteFields({
  draft,
  problems,
  onChange,
}: {
  draft: ObjectDraft;
  problems: DraftProblems;
  onChange: (draft: ObjectDraft) => void;
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label="Название" required error={problems.name} className="sm:col-span-2">
        <input
          value={draft.name}
          onChange={(e) => onChange({ ...draft, name: e.target.value })}
          placeholder="Жилой дом, ул. Строителей, 5"
          className={inputClass}
          maxLength={300}
        />
      </Field>
      <Field label="Тип объекта" hint="От типа зависят параметры ТЭП и расчёт графика по МРР">
        <select
          value={draft.objectType}
          onChange={(e) => onChange({ ...draft, objectType: e.target.value as ObjectType })}
          className={selectClass}
        >
          {OBJECT_TYPES.map((type) => (
            <option key={type} value={type}>
              {ru.objectType[type]}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Начало СМР" error={problems.planStart} hint="Первый день графика">
        <input
          type="date"
          value={draft.planStart}
          onChange={(e) => onChange({ ...draft, planStart: e.target.value })}
          className={inputClass}
        />
      </Field>
      <Field label="Адрес" className="sm:col-span-2">
        <input
          value={draft.address}
          onChange={(e) => onChange({ ...draft, address: e.target.value })}
          placeholder="г. Москва, …"
          className={inputClass}
        />
      </Field>
    </div>
  );
}

const TEP_FIELDS: { key: keyof TepDraft; label: string; hint: string }[] = [
  { key: "floors", label: "Этажность", hint: "этажей" },
  { key: "total_area", label: "Площадь квартир", hint: "м²" },
  { key: "sections", label: "Секций", hint: "по умолчанию 1" },
  { key: "piles", label: "Свай", hint: "по умолчанию 0" },
  { key: "shifts", label: "Сменность", hint: "1,5 · 2 · 3" },
];

/**
 * Параметры генератора графика — показывать только для типа с генератором (`hasGenerator`):
 * больше их никто не читает. Допустимые значения сменности знает только plan-service:
 * неподходящее значение он отклонит с перечнем допустимых, экран покажет его ответ.
 */
export function TepFields({
  tep,
  problems,
  onChange,
}: {
  tep: TepDraft;
  problems: DraftProblems;
  onChange: (tep: TepDraft) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      {TEP_FIELDS.map((field) => (
        <Field key={field.key} label={field.label} hint={field.hint} error={problems[field.key]}>
          <input
            inputMode="decimal"
            value={tep[field.key]}
            onChange={(e) => onChange({ ...tep, [field.key]: e.target.value })}
            className={`${inputClass} tabular-nums`}
          />
        </Field>
      ))}
    </div>
  );
}

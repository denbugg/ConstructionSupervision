/**
 * Черновик правила «этап → техника»: правки копятся здесь и уходят одним сохранением.
 * Чистые функции без React — их легко проверить глазами и нельзя сломать рендером.
 * Форма повторяет `RuleUpdate` plan-service (docs/methodology.md, раздел 5).
 */
import type { RuleRead } from "@/shared/api/queries";
import type { StageLabel } from "@/shared/locale/ru";

export type Group = { any_of: string[]; min: number };

export type RuleDraft = {
  required: Group[];
  allowed: string[];
  signature: { equipment: string[]; stage_label: StageLabel | null };
  min_sessions: number;
  is_active: boolean;
};

/** Новое правило: пустое, как предлагает plan-service; `min_sessions` — по умолчанию методики. */
export const EMPTY_DRAFT: RuleDraft = {
  required: [],
  allowed: [],
  signature: { equipment: [], stage_label: null },
  min_sessions: 2,
  is_active: true,
};

export function fromRule(rule: RuleRead): RuleDraft {
  return {
    required: rule.required.map((g) => ({ any_of: [...g.any_of], min: g.min })),
    // Поля со значением по умолчанию в схеме сервиса типы считают необязательными.
    allowed: [...(rule.allowed ?? [])],
    signature: {
      equipment: [...(rule.signature.equipment ?? [])],
      stage_label: rule.signature.stage_label ?? null,
    },
    min_sessions: rule.min_sessions,
    is_active: rule.is_active,
  };
}

/** Тело PATCH/POST: списки и сигнатура заменяются целиком (plan-service README). */
export function toBody(draft: RuleDraft) {
  return {
    required: draft.required,
    allowed: draft.allowed,
    signature: draft.signature,
    min_sessions: draft.min_sessions,
    is_active: draft.is_active,
  };
}

export function sameDraft(a: RuleDraft, b: RuleDraft): boolean {
  return JSON.stringify(toBody(a)) === JSON.stringify(toBody(b));
}

const add = (list: string[], code: string) => (list.includes(code) ? list : [...list, code]);
const drop = (list: string[], code: string) => list.filter((c) => c !== code);

export type Action =
  | { type: "reset"; draft: RuleDraft }
  | { type: "addGroup" }
  | { type: "removeGroup"; index: number }
  | { type: "groupAdd"; index: number; code: string }
  | { type: "groupRemove"; index: number; code: string }
  | { type: "groupMin"; index: number; min: number }
  | { type: "allowedAdd"; code: string }
  | { type: "allowedRemove"; code: string }
  | { type: "signatureAdd"; code: string }
  | { type: "signatureRemove"; code: string }
  | { type: "stageLabel"; label: StageLabel | null }
  | { type: "minSessions"; value: number }
  | { type: "active"; value: boolean };

export function reduce(draft: RuleDraft, action: Action): RuleDraft {
  const groups = (fn: (g: Group, i: number) => Group) => ({
    ...draft,
    required: draft.required.map(fn),
  });
  switch (action.type) {
    case "reset":
      return action.draft;
    case "addGroup":
      return { ...draft, required: [...draft.required, { any_of: [], min: 1 }] };
    case "removeGroup":
      return { ...draft, required: draft.required.filter((_, i) => i !== action.index) };
    case "groupAdd":
      return groups((g, i) => (i === action.index ? { ...g, any_of: add(g.any_of, action.code) } : g));
    case "groupRemove":
      return groups((g, i) => (i === action.index ? { ...g, any_of: drop(g.any_of, action.code) } : g));
    case "groupMin":
      return groups((g, i) => (i === action.index ? { ...g, min: Math.max(1, action.min) } : g));
    case "allowedAdd":
      return { ...draft, allowed: add(draft.allowed, action.code) };
    case "allowedRemove":
      return { ...draft, allowed: drop(draft.allowed, action.code) };
    case "signatureAdd":
      return {
        ...draft,
        signature: { ...draft.signature, equipment: add(draft.signature.equipment, action.code) },
      };
    case "signatureRemove":
      return {
        ...draft,
        signature: { ...draft.signature, equipment: drop(draft.signature.equipment, action.code) },
      };
    case "stageLabel":
      return { ...draft, signature: { ...draft.signature, stage_label: action.label } };
    case "minSessions":
      return { ...draft, min_sessions: Math.max(1, action.value) };
    case "active":
      return { ...draft, is_active: action.value };
  }
}

/**
 * Что мешает сохранить: пустая группа «любой из» ничего не требует, а сервис её не примет.
 * Пустой список — сохранять можно.
 */
export function problems(draft: RuleDraft): string[] {
  const issues: string[] = [];
  draft.required.forEach((g, i) => {
    if (g.any_of.length === 0) issues.push(`Группа ${i + 1}: выберите хотя бы один класс`);
  });
  if (draft.required.length === 0 && draft.signature.equipment.length === 0 && !draft.signature.stage_label) {
    issues.push("Правило пустое: нет ни обязательной техники, ни сигнатуры — по нему нечего проверять");
  }
  return issues;
}

import type { ReactNode } from "react";

/** Общие классы полей: один вид у ввода, списка и многострочного поля на всех экранах. */
const base =
  "rounded-lg border-0 bg-white text-sm text-ink shadow-sm ring-1 ring-inset ring-ink/15 placeholder:text-muted/60 focus:outline-none focus:ring-2 focus:ring-accent disabled:bg-stone-100 disabled:text-muted";

/**
 * Класс поля с размером и шириной. Высота и ширина задаются только здесь: дописанный снаружи
 * `w-auto` к `w-full` не всегда побеждает — порядок в CSS решает сборщик, а не строка классов.
 */
export function fieldClass(kind: "input" | "select", size: "sm" | "md" = "md", width = "w-full"): string {
  const height = size === "sm" ? "h-8" : "h-9";
  const padding = kind === "select" ? "pl-3 pr-8" : size === "sm" ? "px-2.5" : "px-3";
  return `${base} ${height} ${padding} ${width}`;
}

export const inputClass = fieldClass("input");
export const selectClass = fieldClass("select");
export const textareaClass = `${base} w-full px-3 py-2`;

/** Поле формы: подпись, само поле, подсказка или ошибка под ним. */
export function Field({
  label,
  hint,
  error,
  required = false,
  className = "",
  children,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  required?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <label className={`block space-y-1.5 ${className}`}>
      <span className="block text-[13px] font-medium text-ink/85">
        {label}
        {required && <span className="text-accent"> *</span>}
      </span>
      {children}
      {error ? (
        <span className="block text-xs text-red-700">{error}</span>
      ) : (
        hint && <span className="block text-xs text-muted">{hint}</span>
      )}
    </label>
  );
}

/** Переключатель «вкл/выкл» для флагов: правило включено, камера активна. */
export function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className={`inline-flex items-center gap-2 text-sm ${disabled ? "opacity-50" : "cursor-pointer"}`}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${checked ? "bg-emerald-600" : "bg-ink/20"}`}
      >
        <span
          className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${checked ? "left-[18px]" : "left-0.5"}`}
        />
      </button>
      {label}
    </label>
  );
}

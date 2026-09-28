import type { ReactNode } from "react";

import { Icon, type IconName } from "@/shared/ui/Icon";

/** Шапка экрана: название, одна строка о том, зачем он, и действия экрана справа. */
export function PageHeader({
  title,
  description,
  actions,
  meta,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  /** Строка под описанием: бейджи, «на момент анализа». */
  meta?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div className="min-w-0 max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
        {meta && <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted">{meta}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Карточка-блок экрана с необязательным заголовком и действиями. */
export function Panel({
  title,
  description,
  actions,
  icon,
  children,
  className = "",
  bodyClassName = "p-5",
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  icon?: IconName;
  children?: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`rounded-2xl bg-white shadow-sm ring-1 ring-ink/[0.07] ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-ink/[0.07] px-5 py-3.5">
          <div className="flex min-w-0 items-center gap-2.5">
            {icon && <Icon name={icon} size={17} className="text-muted" />}
            <div className="min-w-0">
              {title && <h2 className="font-semibold">{title}</h2>}
              {description && <p className="text-[13px] text-muted">{description}</p>}
            </div>
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

/** Сегментный переключатель: 2–5 взаимоисключающих вариантов (фильтр статуса, масштаб). */
export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  size = "md",
}: {
  value: T;
  options: { value: T; label: ReactNode; count?: number | null }[];
  onChange: (value: T) => void;
  size?: "sm" | "md";
}) {
  const height = size === "sm" ? "h-7 text-[13px]" : "h-8 text-sm";
  return (
    <div className="inline-flex rounded-lg bg-ink/[0.06] p-0.5" role="tablist">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={String(option.value)}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(option.value)}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 font-medium transition-colors ${height} ${
              active ? "bg-white text-ink shadow-sm" : "text-ink/60 hover:text-ink"
            }`}
          >
            {option.label}
            {option.count != null && (
              <span className={`rounded px-1 text-xs tabular-nums ${active ? "bg-ink/[0.07]" : "bg-ink/[0.05]"}`}>
                {option.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Показатель: подпись, крупное значение, пояснение, откуда число. */
export function Stat({
  label,
  value,
  hint,
  tone = "",
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  tone?: string;
}) {
  return (
    <div className="min-w-0">
      <p className="text-[13px] text-muted">{label}</p>
      <p className={`mt-0.5 text-2xl font-semibold tabular-nums tracking-tight ${tone}`}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
    </div>
  );
}

/** Контейнер содержимого экрана: одна ширина и поля на всех страницах. */
export function PageContainer({ children }: { children: ReactNode }) {
  return <div className="mx-auto w-full max-w-[1480px] px-4 py-6 sm:px-6 lg:px-8">{children}</div>;
}

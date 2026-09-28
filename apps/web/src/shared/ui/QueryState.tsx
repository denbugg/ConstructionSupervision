import type { ReactNode } from "react";

import { ApiError } from "@/shared/api/client";
import { ru } from "@/shared/locale/ru";
import { Icon, type IconName } from "@/shared/ui/Icon";

/** Индикатор ожидания в строку: цвет — текущего текста. */
export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-current border-r-transparent ${className}`}
      aria-hidden="true"
    />
  );
}

/** Загрузка: одна строка, без скелетонов — данных немного, ответ быстрый. */
export function Loading({ label = ru.states.loading }: { label?: string }) {
  return (
    <p className="flex items-center gap-2 py-3 text-sm text-muted" role="status">
      <Spinner />
      {label}
    </p>
  );
}

/**
 * Пусто — всегда с объяснением, почему и что сделать: пустота без слов — дефект. Действие
 * (`action`) — кнопка, которая это исправляет, если исправить можно отсюда.
 */
export function Empty({
  children,
  title,
  icon,
  action,
}: {
  children?: ReactNode;
  title?: string;
  icon?: IconName;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-ink/20 bg-white/40 px-6 py-8 text-center">
      {icon && (
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-ink/[0.06] text-muted">
          <Icon name={icon} size={20} />
        </span>
      )}
      {title && <p className="font-semibold">{title}</p>}
      {children && <div className="max-w-xl text-sm text-muted">{children}</div>}
      {action && <div className="mt-1 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

/**
 * Ошибка API: сообщение сервиса и `request_id` мелким шрифтом — по нему ошибку находят
 * в логах за секунды (apps/web/README.md, §5).
 */
export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const api = error instanceof ApiError ? error : null;
  return (
    <div className="flex gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-red-900" role="alert">
      <Icon name="alert" size={18} className="mt-0.5 text-red-700" />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-medium">{ru.states.error}</p>
        <p className="text-sm">{errorText(error)}</p>
        {api?.requestId && (
          <p className="text-xs text-red-800/70">
            {ru.states.requestId}: {api.requestId}
          </p>
        )}
        {onRetry && (
          <button type="button" onClick={onRetry} className="text-sm font-medium underline">
            {ru.states.retry}
          </button>
        )}
      </div>
    </div>
  );
}

/** Текст ошибки для человека: `message` сервиса или текст исключения. */
export function errorText(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

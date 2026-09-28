import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { ApiError } from "@/shared/api/client";
import { ru } from "@/shared/locale/ru";
import { Icon } from "@/shared/ui/Icon";
import { errorText } from "@/shared/ui/QueryState";

type Tone = "success" | "error" | "info";
type Toast = { id: number; tone: Tone; title: string; detail?: string };

type ToastApi = {
  success: (title: string, detail?: string) => void;
  info: (title: string, detail?: string) => void;
  /** Ошибка API — с `message` сервиса и `request_id`, как в ErrorBox. */
  error: (error: unknown, title?: string) => void;
};

const ToastContext = createContext<ToastApi>({
  success: () => undefined,
  info: () => undefined,
  error: () => undefined,
});

// Ошибку держим дольше: её читают и переписывают request_id.
const LIFETIME: Record<Tone, number> = { success: 4500, info: 4500, error: 9000 };

const TONE: Record<Tone, { icon: "check" | "alert" | "info"; ring: string; iconBg: string }> = {
  success: { icon: "check", ring: "ring-emerald-200", iconBg: "bg-emerald-100 text-emerald-700" },
  error: { icon: "alert", ring: "ring-red-200", iconBg: "bg-red-100 text-red-700" },
  info: { icon: "info", ring: "ring-ink/10", iconBg: "bg-ink/[0.06] text-ink/70" },
};

/** Короткие уведомления о результате действия: «сохранено», «отчёт готов», ошибка сервиса. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);

  const dismiss = useCallback((id: number) => setToasts((all) => all.filter((t) => t.id !== id)), []);
  const push = useCallback(
    (tone: Tone, title: string, detail?: string) => {
      const id = next.current++;
      setToasts((all) => [...all.slice(-3), { id, tone, title, detail }]);
      window.setTimeout(() => dismiss(id), LIFETIME[tone]);
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(
    () => ({
      success: (title, detail) => push("success", title, detail),
      info: (title, detail) => push("info", title, detail),
      error: (error, title = "Не получилось") => {
        const requestId = error instanceof ApiError ? error.requestId : null;
        const detail = `${errorText(error)}${requestId ? ` · ${ru.states.requestId}: ${requestId}` : ""}`;
        push("error", title, detail);
      },
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      {createPortal(
        <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className={`pointer-events-auto flex animate-slide-in gap-3 rounded-xl bg-white p-3.5 shadow-lg ring-1 ${TONE[toast.tone].ring}`}
            >
              <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${TONE[toast.tone].iconBg}`}>
                <Icon name={TONE[toast.tone].icon} size={15} />
              </span>
              <div className="min-w-0 flex-1 pt-0.5">
                <p className="text-sm font-medium">{toast.title}</p>
                {toast.detail && <p className="mt-0.5 break-words text-[13px] text-muted">{toast.detail}</p>}
              </div>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                aria-label="Закрыть уведомление"
                className="h-6 w-6 shrink-0 rounded text-muted hover:bg-ink/5 hover:text-ink"
              >
                <Icon name="x" size={14} className="mx-auto" />
              </button>
            </div>
          ))}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  return useContext(ToastContext);
}

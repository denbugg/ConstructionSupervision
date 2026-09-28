import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { Button, IconButton } from "@/shared/ui/Button";

type ModalProps = {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  /** Есть — тело и подвал оборачиваются формой: Enter отправляет её. */
  onSubmit?: () => void;
  /** Идёт запрос: закрыть щелчком мимо или Esc нельзя, чтобы не потерять результат. */
  busy?: boolean;
  size?: "sm" | "md" | "lg";
};

const WIDTH = { sm: "max-w-md", md: "max-w-xl", lg: "max-w-3xl" };

/** Диалог поверх экрана: Esc и щелчок по фону закрывают, фокус — на первое поле. */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  onSubmit,
  busy = false,
  size = "md",
}: ModalProps) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onClose]);

  useEffect(() => {
    if (!open) return;
    const first = panel.current?.querySelector<HTMLElement>(
      "input:not([type=hidden]):not([disabled]), select, textarea, [data-autofocus]",
    );
    (first ?? panel.current)?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
    };
  }, [open]);

  if (!open) return null;

  const body = (
    <>
      {children && <div className="max-h-[65vh] overflow-y-auto px-6 py-5">{children}</div>}
      {footer && (
        <footer className="flex flex-wrap items-center justify-end gap-2 rounded-b-2xl border-t border-ink/10 bg-stone-50 px-6 py-3.5">
          {footer}
        </footer>
      )}
    </>
  );
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!busy) onSubmit?.();
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-start justify-center overflow-y-auto bg-ink/45 p-4 pt-[8vh] backdrop-blur-[2px]"
      onMouseDown={(e) => e.target === e.currentTarget && !busy && onClose()}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`w-full ${WIDTH[size]} animate-pop-in rounded-2xl bg-white shadow-2xl ring-1 ring-ink/10 focus:outline-none`}
      >
        <header className="flex items-start gap-4 border-b border-ink/10 px-6 py-4">
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-lg font-semibold">
              {title}
            </h2>
            {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
          </div>
          <IconButton icon="x" label="Закрыть" size="sm" onClick={onClose} disabled={busy} />
        </header>
        {onSubmit ? <form onSubmit={submit}>{body}</form> : body}
      </div>
    </div>,
    document.body,
  );
}

type ConfirmOptions = {
  title: string;
  message?: ReactNode;
  confirmLabel?: string;
  tone?: "danger" | "primary";
};

type Pending = ConfirmOptions & { resolve: (ok: boolean) => void };

const ConfirmContext = createContext<(options: ConfirmOptions) => Promise<boolean>>(() =>
  Promise.resolve(false),
);

/**
 * Подтверждение необратимых и дорогих действий (архив, замена графика) — своим диалогом, а
 * не `window.confirm`: у того нет ни объяснения последствий, ни вида интерфейса.
 */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);
  const confirm = useCallback(
    (options: ConfirmOptions) =>
      new Promise<boolean>((resolve) => setPending({ ...options, resolve })),
    [],
  );
  const close = (ok: boolean) => {
    pending?.resolve(ok);
    setPending(null);
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Modal
        open={pending != null}
        onClose={() => close(false)}
        title={pending?.title}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => close(false)}>
              Отмена
            </Button>
            <Button
              variant={pending?.tone === "danger" ? "danger" : "primary"}
              onClick={() => close(true)}
              data-autofocus
            >
              {pending?.confirmLabel ?? "Продолжить"}
            </Button>
          </>
        }
      >
        {pending?.message && <div className="space-y-2 text-sm text-ink/80">{pending.message}</div>}
      </Modal>
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  return useContext(ConfirmContext);
}

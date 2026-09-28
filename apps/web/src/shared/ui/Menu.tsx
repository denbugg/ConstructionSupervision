import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { buttonClass, type ButtonSize, type ButtonVariant } from "@/shared/ui/Button";
import { Icon, type IconName } from "@/shared/ui/Icon";

export type MenuItem =
  | {
      label: string;
      icon?: IconName;
      onSelect: () => void;
      tone?: "danger";
      disabled?: boolean;
      hint?: string;
    }
  | "divider";

// Выше этого расстояния до низа окна список раскрывается вверх.
const FLIP_BELOW = 320;

/**
 * Выпадающее меню действий («⋯»). Редкие и опасные действия живут здесь, а не рядом с
 * главной кнопкой: их не нажмёшь случайно, но и искать не нужно. Список рисуется в портале с
 * фиксированной позицией — таблица с прокруткой его не обрежет.
 */
export function Menu({
  items,
  label = "Действия",
  trigger,
  variant = "ghost",
  size = "md",
  align = "right",
}: {
  items: MenuItem[];
  label?: string;
  /** Подпись кнопки; без неё — квадратная кнопка «⋯». */
  trigger?: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  align?: "left" | "right";
}) {
  const [position, setPosition] = useState<CSSProperties | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const open = position != null;

  const place = () => {
    const rect = button.current?.getBoundingClientRect();
    if (!rect) return;
    const up = window.innerHeight - rect.bottom < FLIP_BELOW && rect.top > FLIP_BELOW;
    setPosition({
      position: "fixed",
      ...(up ? { bottom: window.innerHeight - rect.top + 6 } : { top: rect.bottom + 6 }),
      ...(align === "right" ? { right: window.innerWidth - rect.right } : { left: rect.left }),
    });
  };

  useLayoutEffect(() => {
    if (open) list.current?.querySelector<HTMLElement>("[role=menuitem]:not(:disabled)")?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const close = () => setPosition(null);
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (!button.current?.contains(target) && !list.current?.contains(target)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", close, true);
    };
  }, [open]);

  const square = trigger ? "" : size === "sm" ? "!w-8 !px-0" : "!w-9 !px-0";
  return (
    <>
      <button
        ref={button}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        title={trigger ? undefined : label}
        onClick={(e) => {
          e.stopPropagation();
          if (open) setPosition(null);
          else place();
        }}
        className={`${buttonClass(variant, size)} ${square}`}
      >
        {trigger ?? <Icon name="more" size={17} />}
        {trigger && <Icon name="chevronDown" size={14} className="-mr-1 opacity-60" />}
      </button>
      {open &&
        createPortal(
          <div
            ref={list}
            role="menu"
            style={position}
            onClick={(e) => e.stopPropagation()}
            className="z-[55] min-w-56 animate-pop-in overflow-hidden rounded-xl bg-white py-1.5 text-ink shadow-xl ring-1 ring-ink/10"
          >
            {items.map((item, i) =>
              item === "divider" ? (
                <div key={`d${i}`} className="my-1.5 border-t border-ink/10" />
              ) : (
                <button
                  key={item.label}
                  type="button"
                  role="menuitem"
                  disabled={item.disabled}
                  onClick={() => {
                    setPosition(null);
                    item.onSelect();
                  }}
                  className={`flex w-full items-start gap-2.5 px-3.5 py-2 text-left text-sm outline-none disabled:opacity-40 ${
                    item.tone === "danger" ? "text-red-700 hover:bg-red-50 focus:bg-red-50" : "hover:bg-ink/[0.05] focus:bg-ink/[0.05]"
                  }`}
                >
                  {item.icon && <Icon name={item.icon} size={16} className="mt-0.5 opacity-70" />}
                  <span>
                    {item.label}
                    {item.hint && <span className="block text-xs text-muted">{item.hint}</span>}
                  </span>
                </button>
              ),
            )}
          </div>,
          document.body,
        )}
    </>
  );
}

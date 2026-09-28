import type { ReactNode } from "react";

/** Бейдж статуса: цвет задаёт вызывающий, чтобы значения перечислений не жили здесь. */
export function Badge({
  tone,
  children,
  size = "md",
}: {
  tone: string;
  children: ReactNode;
  size?: "sm" | "md";
}) {
  const box = size === "sm" ? "px-1.5 py-px text-[11px]" : "px-2 py-0.5 text-xs";
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-md font-medium ${box} ${tone}`}>
      {children}
    </span>
  );
}

/** Цветная точка статуса: там, где бейдж занял бы слишком много места. */
export function Dot({ className }: { className: string }) {
  return <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${className}`} aria-hidden="true" />;
}

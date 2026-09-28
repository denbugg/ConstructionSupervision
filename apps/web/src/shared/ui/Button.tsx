import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";

import { Icon, type IconName } from "@/shared/ui/Icon";
import { Spinner } from "@/shared/ui/QueryState";

/**
 * Кнопки. Одна главная (`primary`, цвет акцента) на экран или на диалог — то действие, ради
 * которого человек сюда пришёл; остальные — `secondary` или `ghost`.
 */
export type ButtonVariant = "primary" | "dark" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

const VARIANT: Record<ButtonVariant, string> = {
  primary: "bg-accent text-white shadow-sm hover:bg-[#a93b15] disabled:bg-accent/50",
  dark: "bg-ink text-white shadow-sm hover:bg-ink/85 disabled:bg-ink/40",
  secondary:
    "bg-white text-ink shadow-sm ring-1 ring-inset ring-ink/15 hover:bg-stone-50 hover:ring-ink/25 disabled:text-ink/40",
  ghost: "text-ink/75 hover:bg-ink/[0.06] hover:text-ink disabled:text-ink/30",
  danger: "bg-red-700 text-white shadow-sm hover:bg-red-800 disabled:bg-red-700/50",
};

const SIZE: Record<ButtonSize, string> = {
  sm: "h-8 gap-1.5 rounded-md px-2.5 text-[13px]",
  md: "h-9 gap-2 rounded-lg px-3.5 text-sm",
  lg: "h-11 gap-2 rounded-lg px-5 text-[15px]",
};

export function buttonClass(variant: ButtonVariant = "secondary", size: ButtonSize = "md"): string {
  return `inline-flex shrink-0 items-center justify-center whitespace-nowrap font-medium transition-colors disabled:cursor-not-allowed ${VARIANT[variant]} ${SIZE[size]}`;
}

type Own = {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: IconName;
  /** Идёт запрос: кнопка заблокирована, вместо иконки — индикатор. */
  loading?: boolean;
  children?: ReactNode;
};

export function Button({
  variant,
  size,
  icon,
  loading = false,
  disabled,
  className = "",
  children,
  type = "button",
  ...rest
}: Own & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={`${buttonClass(variant, size)} ${className}`}
      {...rest}
    >
      {loading ? <Spinner /> : icon && <Icon name={icon} size={size === "sm" ? 15 : 16} />}
      {children}
    </button>
  );
}

export function ButtonLink({
  variant,
  size,
  icon,
  className = "",
  children,
  ...rest
}: Omit<Own, "loading"> & LinkProps) {
  return (
    <Link className={`${buttonClass(variant, size)} ${className}`} {...rest}>
      {icon && <Icon name={icon} size={size === "sm" ? 15 : 16} />}
      {children}
    </Link>
  );
}

/** Квадратная кнопка с одной иконкой; подпись обязательна — для экранного диктора и подсказки. */
export function IconButton({
  icon,
  label,
  variant = "ghost",
  size = "md",
  className = "",
  ...rest
}: { icon: IconName; label: string; variant?: ButtonVariant; size?: ButtonSize } & Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "children"
>) {
  const box = size === "sm" ? "!w-8 !px-0" : size === "lg" ? "!w-11 !px-0" : "!w-9 !px-0";
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={`${buttonClass(variant, size)} ${box} ${className}`}
      {...rest}
    >
      <Icon name={icon} size={size === "sm" ? 15 : 17} />
    </button>
  );
}

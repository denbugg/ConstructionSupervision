/**
 * Цвета и порядок статусов. Порядок серьёзностей — от высокой к низкой, как в ленте
 * отклонений analysis-service; значения — из enums.yaml.
 */

export const SEVERITY_ORDER = ["HIGH", "MEDIUM", "LOW", "INFO"] as const;

const OBJECT_STATUS_TONE: Record<string, string> = {
  ON_TRACK: "bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-600/20",
  AHEAD: "bg-sky-50 text-sky-800 ring-1 ring-inset ring-sky-600/20",
  DELAY: "bg-red-50 text-red-800 ring-1 ring-inset ring-red-600/20",
  UNKNOWN: "bg-stone-100 text-stone-700 ring-1 ring-inset ring-stone-500/20",
};

// Цвет крупного значения статуса на обзоре объекта.
const OBJECT_STATUS_TEXT: Record<string, string> = {
  ON_TRACK: "text-emerald-700",
  AHEAD: "text-sky-700",
  DELAY: "text-red-700",
  UNKNOWN: "text-stone-600",
};

const OBJECT_STATUS_DOT: Record<string, string> = {
  ON_TRACK: "bg-emerald-500",
  AHEAD: "bg-sky-500",
  DELAY: "bg-red-600",
  UNKNOWN: "bg-stone-400",
};

const SEVERITY_TONE: Record<string, string> = {
  HIGH: "bg-red-50 text-red-800 ring-1 ring-inset ring-red-600/20",
  MEDIUM: "bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-600/25",
  LOW: "bg-yellow-50 text-yellow-800 ring-1 ring-inset ring-yellow-600/25",
  INFO: "bg-stone-100 text-stone-700 ring-1 ring-inset ring-stone-500/20",
};

const SEVERITY_DOT: Record<string, string> = {
  HIGH: "bg-red-600",
  MEDIUM: "bg-amber-500",
  LOW: "bg-yellow-400",
  INFO: "bg-stone-400",
};

const DEVIATION_STATUS_TONE: Record<string, string> = {
  NEW: "bg-accent/10 text-accent ring-1 ring-inset ring-accent/25",
  CONFIRMED: "bg-red-50 text-red-800 ring-1 ring-inset ring-red-600/20",
  REJECTED: "bg-stone-100 text-stone-600 line-through ring-1 ring-inset ring-stone-500/20",
  RESOLVED: "bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-600/20",
};

const STAGE_STATUS_TONE: Record<string, string> = {
  NOT_STARTED: "bg-stone-100 text-stone-700 ring-1 ring-inset ring-stone-500/20",
  IN_PROGRESS: "bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-600/25",
  DONE: "bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-600/20",
  LATE: "bg-red-50 text-red-800 ring-1 ring-inset ring-red-600/20",
  AHEAD: "bg-sky-50 text-sky-800 ring-1 ring-inset ring-sky-600/20",
};

// Заливка выполненной части полосы на Ганте — тем же цветом, что бейдж статуса этапа.
const STAGE_STATUS_FILL: Record<string, string> = {
  NOT_STARTED: "fill-stone-400",
  IN_PROGRESS: "fill-amber-500",
  DONE: "fill-emerald-600",
  LATE: "fill-red-600",
  AHEAD: "fill-sky-600",
};

// То же для HTML-полос прогресса на обзоре объекта.
const STAGE_STATUS_BAR: Record<string, string> = {
  NOT_STARTED: "bg-stone-400",
  IN_PROGRESS: "bg-amber-500",
  DONE: "bg-emerald-600",
  LATE: "bg-red-600",
  AHEAD: "bg-sky-600",
};

export function stageStatusTone(status: string | null | undefined): string {
  return STAGE_STATUS_TONE[status ?? "NOT_STARTED"] ?? STAGE_STATUS_TONE.NOT_STARTED!;
}

export function stageStatusFill(status: string | null | undefined): string {
  return STAGE_STATUS_FILL[status ?? "NOT_STARTED"] ?? STAGE_STATUS_FILL.NOT_STARTED!;
}

export function stageStatusBar(status: string | null | undefined): string {
  return STAGE_STATUS_BAR[status ?? "NOT_STARTED"] ?? STAGE_STATUS_BAR.NOT_STARTED!;
}

export function deviationStatusTone(status: string): string {
  return DEVIATION_STATUS_TONE[status] ?? DEVIATION_STATUS_TONE.RESOLVED!;
}

export function objectStatusTone(status: string | null | undefined): string {
  return OBJECT_STATUS_TONE[status ?? "UNKNOWN"] ?? OBJECT_STATUS_TONE.UNKNOWN!;
}

export function objectStatusText(status: string | null | undefined): string {
  return OBJECT_STATUS_TEXT[status ?? "UNKNOWN"] ?? OBJECT_STATUS_TEXT.UNKNOWN!;
}

export function objectStatusDot(status: string | null | undefined): string {
  return OBJECT_STATUS_DOT[status ?? "UNKNOWN"] ?? OBJECT_STATUS_DOT.UNKNOWN!;
}

export function severityTone(severity: string): string {
  return SEVERITY_TONE[severity] ?? SEVERITY_TONE.INFO!;
}

export function severityDot(severity: string): string {
  return SEVERITY_DOT[severity] ?? SEVERITY_DOT.INFO!;
}

/** Сколько открытых отклонений всего: сумма по серьёзностям. */
export function openDeviations(bySeverity: Record<string, number>): number {
  return Object.values(bySeverity).reduce((sum, n) => sum + n, 0);
}

/** Ранг серьёзности для сортировки: меньше — важнее; неизвестная — в конец. */
export function severityRank(severity: string): number {
  const index = (SEVERITY_ORDER as readonly string[]).indexOf(severity);
  return index < 0 ? SEVERITY_ORDER.length : index;
}

/**
 * Итог прогона анализа словами: сколько отклонений открыто после него и что изменилось.
 * Счётчики — из `stats` прогона (analysis-service, services/runs.py).
 */
export function runSummary(stats: Record<string, unknown>): string {
  const n = (key: string) => (typeof stats[key] === "number" ? (stats[key] as number) : null);
  const open = n("deviations_open");
  const changes = [
    n("deviations_opened") ? `новых ${n("deviations_opened")}` : null,
    n("deviations_resolved") ? `закрыто ${n("deviations_resolved")}` : null,
    n("deviations_withdrawn") ? `снято ${n("deviations_withdrawn")}` : null,
  ].filter((part): part is string => part != null);
  const head = open != null ? `Открытых отклонений: ${open}` : "Выводы обновлены";
  return changes.length > 0 ? `${head} (${changes.join(", ")})` : `${head}, без изменений`;
}

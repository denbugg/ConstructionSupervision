import { formatDelay, formatMoment, formatPlanDate } from "@/entities/format";
import type { StageSaveResult } from "@/features/gantt/useGantt";
import { label, ru } from "@/shared/locale/ru";

/** Итог правки этапа: «было → стало» по прогнозу этапа, критическому пути и отставанию объекта. */
export function SaveSummary({ result }: { result: StageSaveResult }) {
  const { before, after } = result;
  const change = (was: string, now: string) => (was === now ? `${now} (без изменений)` : `${was} → ${now}`);
  const objectDelay = (s: StageSaveResult["after"]) =>
    s.status ? `${label(ru.objectStatus, s.status.status)}, ${formatDelay(s.status.delay_days)} ${ru.units.workDays}` : "—";
  const critical = (value: boolean | null) => (value == null ? "—" : value ? "да" : "нет");
  const status = (s: StageSaveResult["after"]) => (s.stage ? label(ru.stageStatus, s.stage.status) : "—");
  return (
    <div className="rounded-xl bg-emerald-50 p-4 text-emerald-950 ring-1 ring-emerald-200">
      <p className="mb-1 font-medium">Сохранено, анализ пересчитан на {formatMoment(result.run.as_of)}:</p>
      <ul className="space-y-0.5">
        <li>статус этапа: {change(status(before), status(after))}</li>
        <li>прогноз окончания этапа: {change(formatPlanDate(before.stage?.forecast_end), formatPlanDate(after.stage?.forecast_end))}</li>
        <li>
          отставание этапа: {change(formatDelay(before.stage?.delay_days), formatDelay(after.stage?.delay_days))} {ru.units.workDays}
        </li>
        <li>на критическом пути: {change(critical(before.critical), critical(after.critical))}</li>
        <li>объект: {change(objectDelay(before), objectDelay(after))}</li>
      </ul>
    </div>
  );
}

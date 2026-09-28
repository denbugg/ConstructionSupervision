import { useState } from "react";

import { formatPlanDate } from "@/entities/format";
import { dayNumber, isoDate, moscowDay } from "@/features/gantt/layout";
import { SaveSummary } from "@/features/gantt/SaveSummary";
import { useSaveStage, type PlanStage } from "@/features/gantt/useGantt";
import { Button } from "@/shared/ui/Button";
import { fieldClass } from "@/shared/ui/Field";
import { Icon } from "@/shared/ui/Icon";
import { useConfirm } from "@/shared/ui/Modal";
import { useToast } from "@/shared/ui/Toast";

/**
 * Отметка оператора «этап выполнен» (T46, ADR-0015): работы приняты, а снимки добрали не всё.
 * Анализ принимает её как факт: этап завершён в дату отметки, последователи считаются от неё,
 * со следующего дня отклонения по этапу не ищутся (methodology.md, 10.3b).
 */
export function StageCompletion({
  objectId,
  stage,
  asOfDay,
}: {
  objectId: string;
  stage: PlanStage;
  /** Сутки момента анализа: отметка позже них в текущем анализе не действует. */
  asOfDay: number | null;
}) {
  const save = useSaveStage(objectId);
  const toast = useToast();
  const confirm = useConfirm();
  // По умолчанию — день момента анализа: более поздняя отметка пересчёт не изменит.
  const [day, setDay] = useState(isoDate(asOfDay ?? moscowDay(new Date().toISOString())));
  const [note, setNote] = useState("");
  const pending = save.isPending;

  const mark = () =>
    save.mutate(
      { stageId: stage.id, patch: { completed_on: day, completion_note: note.trim() || null } },
      {
        onSuccess: () => toast.success("Этап отмечен выполненным", "Анализ пересчитан — итог ниже"),
        onError: (error) => toast.error(error, "Отметка не сохранена"),
      },
    );
  const unmark = async () => {
    const ok = await confirm({
      title: `Снять отметку «выполнен» с этапа «${stage.name}»?`,
      message:
        "Этап снова будет считаться по снимкам: вернутся прогноз по темпу и проверки D1–D10 после даты отметки.",
      confirmLabel: "Снять отметку",
    });
    if (ok)
      save.mutate(
        { stageId: stage.id, patch: { completed_on: null } },
        {
          onSuccess: () => toast.success("Отметка снята", "Анализ пересчитан — итог ниже"),
          onError: (error) => toast.error(error, "Отметка не снята"),
        },
      );
  };

  const marked = stage.completed_on ?? null;
  const shown = marked ?? day;
  const afterAnalysis = asOfDay != null && shown !== "" && dayNumber(shown) > asOfDay;

  return (
    <div
      className={`space-y-3 rounded-xl p-4 text-sm ring-1 ${marked ? "bg-emerald-50/70 ring-emerald-200" : "bg-canvas/50 ring-ink/[0.06]"}`}
    >
      <p className="flex items-center gap-2 font-medium">
        <Icon name="check" size={16} className={marked ? "text-emerald-700" : "text-muted"} />
        {marked ? "Выполнен по отметке оператора" : "Отметка «этап выполнен»"}
      </p>
      {marked ? (
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-0 flex-1 space-y-0.5">
            <p>
              Последний день работ — <b>{formatPlanDate(marked)}</b>
              {stage.completed_by && <>, отметил {stage.completed_by}</>}.
            </p>
            {stage.completion_note && <p className="text-muted">Комментарий: {stage.completion_note}</p>}
          </div>
          <Button icon="x" loading={pending} onClick={unmark}>
            {pending ? "Снимаем и пересчитываем…" : "Снять отметку"}
          </Button>
        </div>
      ) : (
        <>
          <p className="text-xs text-muted">
            Работы приняты, а снимки добрали не всё — камера видела не весь участок. Отметка закроет
            этап последним днём работ: прогноз последователей пойдёт от него, со следующего дня
            отклонения по этапу не ищутся. Кто и когда отметил — видно в карточке и в отчёте.
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Последний день работ</span>
              <input type="date" value={day} onChange={(e) => setDay(e.target.value)} className={fieldClass("input", "md", "w-auto")} />
            </label>
            <label className="flex min-w-[14rem] flex-1 flex-col gap-1">
              <span className="text-xs text-muted">Комментарий, по желанию</span>
              <input
                type="text"
                value={note}
                maxLength={2000}
                placeholder="например, акт приёмки № 12"
                onChange={(e) => setNote(e.target.value)}
                className={fieldClass("input")}
              />
            </label>
            <Button variant="primary" icon="check" disabled={!day} loading={pending} onClick={mark}>
              {pending ? "Отмечаем и пересчитываем…" : "Отметить выполненным"}
            </Button>
          </div>
        </>
      )}
      {afterAnalysis && (
        <p className="flex items-center gap-2 text-amber-800">
          <Icon name="info" size={15} />
          Дата позже момента анализа ({formatPlanDate(isoDate(asOfDay))}): отметка подействует, когда
          анализ дойдёт до этого дня.
        </p>
      )}
      {save.data && <SaveSummary result={save.data} />}
    </div>
  );
}

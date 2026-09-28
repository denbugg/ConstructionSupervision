import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { formatPlanDate } from "@/entities/format";
import { TepFields } from "@/features/objects/ObjectFields";
import { draftFromObject, draftProblems, tepBody, type ObjectDraft } from "@/features/objects/objectDraft";
import {
  generatePlan,
  importPlan,
  useScheduleInvalidation,
  type GenerateResult,
  type ImportResult,
} from "@/features/objects/useObjects";
import { ApiError } from "@/shared/api/client";
import type { ObjectRead } from "@/shared/api/queries";
import type { PlanSchema } from "@/shared/api/schemas";
import { Button } from "@/shared/ui/Button";
import { Field, inputClass } from "@/shared/ui/Field";
import { Icon } from "@/shared/ui/Icon";
import { Modal } from "@/shared/ui/Modal";
import { Segmented } from "@/shared/ui/Page";
import { ErrorBox } from "@/shared/ui/QueryState";

export type PlanMode = "generate" | "import";

type Outcome = { mode: "generate"; result: GenerateResult } | { mode: "import"; result: ImportResult };

/**
 * Построить или заменить график объекта: по нормам МРР-3.2.81-12 или из файла CSV/XLSX.
 * Поверх существующего графика — только явно: ручные правки дат и правил пропадут.
 */
export function PlanSetupDialog({
  object,
  stages,
  open,
  onClose,
  initialMode = "generate",
}: {
  object: ObjectRead;
  /** Сколько этапов в текущем графике; больше нуля — график будет заменён. */
  stages: number;
  open: boolean;
  onClose: () => void;
  initialMode?: PlanMode;
}) {
  const [mode, setMode] = useState<PlanMode>(initialMode);
  const [draft, setDraft] = useState<ObjectDraft>(() => draftFromObject(object));
  const [file, setFile] = useState<File | null>(null);
  const [tried, setTried] = useState(false);
  const invalidate = useScheduleInvalidation();
  const navigate = useNavigate();
  const replace = stages > 0;

  const run = useMutation({
    mutationFn: async (): Promise<Outcome> => {
      if (mode === "import") {
        if (!file) throw new Error("Выберите файл графика");
        return { mode, result: await importPlan(object.id, file, replace) };
      }
      const body: PlanSchema<"PlanGenerateRequest"> = {
        start_date: draft.planStart || null,
        tep: tepBody(draft.tep, object.tep as Record<string, unknown>) as PlanSchema<"PlanGenerateRequest">["tep"],
      };
      return { mode, result: await generatePlan(object.id, body, replace) };
    },
    onSuccess: () => invalidate(),
  });

  const problems = mode === "generate" ? draftProblems(draft, true) : {};
  const blocked = Object.keys(problems).length > 0 || (mode === "import" && !file);
  const submit = () => {
    setTried(true);
    if (!blocked) run.mutate();
  };

  if (run.data) {
    return (
      <Modal
        open={open}
        onClose={onClose}
        title="График построен"
        footer={
          <>
            <Button variant="ghost" onClick={onClose}>
              Готово
            </Button>
            <Button
              variant="primary"
              icon="gantt"
              onClick={() => {
                onClose();
                navigate(`/objects/${object.id}/gantt`);
              }}
            >
              Открыть график
            </Button>
          </>
        }
      >
        <Result outcome={run.data} />
      </Modal>
    );
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={replace ? "Перестроить график" : "Построить график"}
      description="Этапы, связи, критический путь и правила «этап → техника» для каждого этапа."
      size="lg"
      busy={run.isPending}
      onSubmit={submit}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={run.isPending}>
            Отмена
          </Button>
          <Button type="submit" variant={replace ? "danger" : "primary"} loading={run.isPending} icon={mode === "import" ? "upload" : "sparkle"}>
            {replace ? "Заменить график" : mode === "import" ? "Импортировать" : "Сгенерировать"}
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <Segmented
          value={mode}
          onChange={(value) => {
            setMode(value);
            run.reset();
          }}
          options={[
            { value: "generate", label: "По нормам МРР" },
            { value: "import", label: "Из файла CSV / XLSX" },
          ]}
        />

        {replace && (
          <div className="flex gap-3 rounded-xl bg-amber-50 p-3.5 text-sm text-amber-900 ring-1 ring-amber-200">
            <Icon name="alert" size={17} className="mt-0.5 shrink-0" />
            <p>
              Текущий график ({stages} этапов) будет заменён целиком. Ручные правки дат и правил этапов
              пропадут, анализ пересчитается по новому графику.
            </p>
          </div>
        )}

        {mode === "generate" ? (
          <div className="space-y-4">
            <p className="text-sm text-muted">
              Сроки — по МРР-3.2.81-12 (табл. 1, п. 5.1.21) с интерполяцией и коэффициентами, даты —
              по рабочему календарю объекта. У каждого этапа будет указано основание срока.
            </p>
            <Field label="Начало СМР" required error={tried ? problems.planStart : null} className="max-w-xs">
              <input
                type="date"
                value={draft.planStart}
                onChange={(e) => setDraft({ ...draft, planStart: e.target.value })}
                className={inputClass}
              />
            </Field>
            <TepFields tep={draft.tep} problems={tried ? problems : {}} onChange={(tep) => setDraft({ ...draft, tep })} />
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-muted">
              Обязательные столбцы: код, наименование, начало, окончание. Необязательные: тип участка,
              визуальная стадия, связи (<code className="rounded bg-ink/5 px-1">12.3.1 FS+2</code>, через
              запятую), фаза. Недостающее и правила техники берутся из шаблона этапа с тем же кодом.
            </p>
            <Field label="Файл графика" required error={tried && !file ? "Выберите файл" : null}>
              <input
                type="file"
                accept=".csv,.xlsx"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-ink file:px-3 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-ink/85"
              />
            </Field>
          </div>
        )}

        {run.isError && <PlanError error={run.error} />}
      </div>
    </Modal>
  );
}

function Result({ outcome }: { outcome: Outcome }) {
  const { result } = outcome;
  return (
    <div className="space-y-3 text-sm">
      <div className="grid grid-cols-3 gap-3">
        <Fact label="Этапов" value={result.stages} />
        <Fact label="На критическом пути" value={result.critical_stages} />
        <Fact label="С правилами техники" value={result.rules} />
      </div>
      {outcome.mode === "generate" && (
        <>
          <p>
            Срок по нормам — <b>{outcome.result.total_months} мес.</b>: с{" "}
            {formatPlanDate(outcome.result.plan_start)} по {formatPlanDate(outcome.result.plan_end)}.
          </p>
          <p className="text-muted">Основание: {outcome.result.basis}</p>
        </>
      )}
      <p className="text-muted">
        Версия плана {result.plan_version}. Анализ пересчитается сам — выводы на обзоре обновятся
        через несколько секунд.
      </p>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl bg-canvas/70 p-3">
      <p className="text-xs text-muted">{label}</p>
      <p className="text-xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

/** Ошибка построения: у импорта — построчно (`details.errors`: строка, столбец, текст). */
function PlanError({ error }: { error: unknown }) {
  const details = error instanceof ApiError ? error.details : null;
  const rows =
    details != null && typeof details === "object" && "errors" in details && Array.isArray(details.errors)
      ? (details.errors as { row?: number | null; column?: string | null; message?: string }[])
      : [];
  return (
    <div className="space-y-2">
      <ErrorBox error={error} />
      {error instanceof ApiError && error.code === "NORMS_NOT_AVAILABLE" && (
        <p className="text-sm text-muted">Для этого типа объекта норм нет — импортируйте график из файла.</p>
      )}
      {rows.length > 0 && (
        <ul className="max-h-48 space-y-1 overflow-y-auto rounded-xl bg-red-50/60 p-3 text-sm text-red-900">
          {rows.map((row, i) => (
            <li key={i}>
              {row.row != null && <b>Строка {row.row}</b>}
              {row.column && <span>, столбец «{row.column}»</span>}
              {(row.row != null || row.column) && ": "}
              {row.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

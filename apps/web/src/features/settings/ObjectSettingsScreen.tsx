import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { formatMoment, formatPlanDate } from "@/entities/format";
import { planQuery } from "@/features/gantt/useGantt";
import { RequisiteFields, TepFields } from "@/features/objects/ObjectFields";
import { draftFromObject, draftProblems, type Lifecycle, type ObjectDraft } from "@/features/objects/objectDraft";
import { PlanSetupDialog, type PlanMode } from "@/features/objects/PlanSetupDialog";
import { useObjectActions } from "@/features/objects/useObjectActions";
import { useUpdateObject } from "@/features/objects/useObjects";
import { objectQuery, type ObjectRead } from "@/shared/api/queries";
import { ru } from "@/shared/locale/ru";
import { Button, ButtonLink } from "@/shared/ui/Button";
import { Field, selectClass } from "@/shared/ui/Field";
import { PageHeader, Panel } from "@/shared/ui/Page";
import { ErrorBox, Loading } from "@/shared/ui/QueryState";
import { useToast } from "@/shared/ui/Toast";

/** Настройки объекта: реквизиты и ТЭП, график (построить, перестроить), архив. */
export function ObjectSettingsScreen() {
  const { objectId = "" } = useParams();
  const object = useQuery(objectQuery(objectId));
  if (!object.data) return <Loading />;
  return (
    <div className="space-y-5">
      <PageHeader
        title="Реквизиты и график"
        description="Реквизиты и параметры объекта, построение графика по нормам или из файла, архив."
      />
      {/* Ключ — момент правки: после сохранения форма берёт значения с сервера. */}
      <RequisitesPanel key={object.data.updated_at} object={object.data} />
      <SchedulePanel object={object.data} />
      <ArchivePanel object={object.data} />
    </div>
  );
}

function RequisitesPanel({ object }: { object: ObjectRead }) {
  const initial = draftFromObject(object);
  const [draft, setDraft] = useState<ObjectDraft>(initial);
  const update = useUpdateObject(object);
  const toast = useToast();
  const problems = draftProblems(draft, false);
  const changed = JSON.stringify(draft) !== JSON.stringify(initial);

  return (
    <Panel title="Реквизиты" icon="building" bodyClassName="p-5 space-y-6">
      <RequisiteFields draft={draft} problems={problems} onChange={setDraft} />
      {object.status !== "ARCHIVED" && (
        <Field label="Состояние" className="max-w-xs">
          <select value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value as Lifecycle })} className={selectClass}>
            <option value="DRAFT">{ru.objectLifecycle.DRAFT}</option>
            <option value="ACTIVE">{ru.objectLifecycle.ACTIVE}</option>
          </select>
        </Field>
      )}
      <div className="space-y-2.5">
        <p className="text-[13px] font-medium text-ink/85">Параметры объекта (ТЭП) — для генератора графика</p>
        <TepFields tep={draft.tep} problems={problems} onChange={(tep) => setDraft({ ...draft, tep })} />
      </div>
      {update.isError && <ErrorBox error={update.error} />}
      <div className="flex flex-wrap items-center gap-2 border-t border-ink/[0.07] pt-4">
        <Button
          variant="primary"
          icon="check"
          disabled={!changed || Object.keys(problems).length > 0}
          loading={update.isPending}
          onClick={() => update.mutate(draft, { onSuccess: () => toast.success("Реквизиты сохранены") })}
        >
          Сохранить
        </Button>
        <Button variant="ghost" disabled={!changed || update.isPending} onClick={() => setDraft(initial)}>
          Отменить правки
        </Button>
        <span className="ml-auto text-xs text-muted">Изменён {formatMoment(object.updated_at)}</span>
      </div>
    </Panel>
  );
}

function SchedulePanel({ object }: { object: ObjectRead }) {
  const plan = useQuery(planQuery(object.id));
  const [mode, setMode] = useState<PlanMode | null>(null);
  const navigate = useNavigate();
  const stages = plan.data?.stages ?? [];
  const base = `/objects/${object.id}`;
  const first = stages.reduce<string | null>((min, s) => (min == null || s.plan_start < min ? s.plan_start : min), null);
  const last = stages.reduce<string | null>((max, s) => (max == null || s.plan_end > max ? s.plan_end : max), null);

  return (
    <Panel
      title="График работ"
      icon="gantt"
      bodyClassName="p-5 space-y-4"
      actions={
        stages.length > 0 && (
          <ButtonLink to={`${base}/gantt`} size="sm" variant="ghost" icon="gantt">
            Открыть Гант
          </ButtonLink>
        )
      }
    >
      {plan.isPending && <Loading />}
      {plan.isError && <ErrorBox error={plan.error} onRetry={() => plan.refetch()} />}
      {plan.data && (
        <>
          {stages.length === 0 ? (
            <p className="text-sm text-muted">
              Графика нет: без него не с чем сверять факт. Постройте его по нормам МРР-3.2.81-12 из
              этажности и площади или загрузите из файла.
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Fact label="Этапов" value={String(stages.length)} />
              <Fact label="На критическом пути" value={String(stages.filter((s) => s.is_critical).length)} />
              <Fact label="Срок" value={`${formatPlanDate(first)} — ${formatPlanDate(last)}`} />
              <Fact label="Календарь · версия" value={`${plan.data.calendar.code} · v${plan.data.plan_version}`} />
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button variant={stages.length === 0 ? "primary" : "secondary"} icon="sparkle" onClick={() => setMode("generate")}>
              {stages.length === 0 ? "Сгенерировать по МРР" : "Перестроить по МРР"}
            </Button>
            <Button icon="upload" onClick={() => setMode("import")}>
              Импортировать из файла
            </Button>
            {stages.length > 0 && (
              <Button variant="ghost" icon="rules" onClick={() => navigate(`${base}/settings/rules`)}>
                Правила «этап → техника»
              </Button>
            )}
          </div>
        </>
      )}
      {mode && (
        <PlanSetupDialog object={object} stages={stages.length} initialMode={mode} open onClose={() => setMode(null)} />
      )}
    </Panel>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-canvas/60 p-3">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-0.5 font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function ArchivePanel({ object }: { object: ObjectRead }) {
  const actions = useObjectActions();
  const navigate = useNavigate();
  const archived = object.status === "ARCHIVED";
  return (
    <Panel title="Архив" icon="archive" bodyClassName="p-5 flex flex-wrap items-center gap-4">
      <p className="flex-1 text-sm text-muted">
        {archived
          ? "Объект в архиве: его нет в списке действующих, данные сохранены. Вернуть в работу можно в любой момент."
          : "Завершённый или ошибочно заведённый объект уходит в архив. Ничего не удаляется: снимки, выводы и отчёты остаются."}
      </p>
      {archived ? (
        <Button icon="restore" onClick={() => actions.restore(object)} loading={actions.busy}>
          Вернуть в работу
        </Button>
      ) : (
        <Button variant="danger" icon="archive" onClick={() => actions.archive(object, () => navigate("/objects"))} loading={actions.busy}>
          Перевести в архив
        </Button>
      )}
    </Panel>
  );
}

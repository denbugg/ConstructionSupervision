import { useQuery } from "@tanstack/react-query";
import { useReducer, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { formatPlanDate } from "@/entities/format";
import { isZoneType } from "@/entities/zones";
import {
  EMPTY_DRAFT,
  fromRule,
  problems,
  reduce,
  sameDraft,
  type Action,
  type RuleDraft,
} from "@/features/rules-editor/draft";
import {
  useDeleteRule,
  useSaveRule,
  useSelectedStage,
  type SaveResult,
} from "@/features/rules-editor/useRulesEditor";
import { equipmentClassesQuery, type DeviationRead, type StageRead } from "@/shared/api/queries";
import { ru, type StageLabel } from "@/shared/locale/ru";
import { Dot } from "@/shared/ui/Badge";
import { Button, ButtonLink } from "@/shared/ui/Button";
import { Toggle, fieldClass } from "@/shared/ui/Field";
import { Icon } from "@/shared/ui/Icon";
import { useConfirm } from "@/shared/ui/Modal";
import { PageHeader } from "@/shared/ui/Page";
import { Empty, ErrorBox, Loading } from "@/shared/ui/QueryState";
import { useToast } from "@/shared/ui/Toast";

// Людей правило этапа не касается: они участвуют только в D6 (methodology.md, раздел 6).
const NOT_EQUIPMENT = "person";
const STAGE_LABELS = Object.keys(ru.stageLabel) as StageLabel[];

/**
 * Редактор правил «этап → техника»: логика — данные, а не код. Меняем правило —
 * анализ пересчитывает ленту, и видно, какие отклонения исчезли или появились.
 */
export function RulesEditorScreen() {
  const { objectId = "" } = useParams();
  const { stages, items, stage, select } = useSelectedStage(objectId);

  return (
    <div>
      <PageHeader
        title="Правила «этап → техника»"
        description="Какая техника обязательна на этапе, какая допустима и по какому признаку этап считается начатым. Сохранение пересчитывает ленту предупреждений."
      />

      {stages.isPending && <Loading />}
      {stages.isError && <ErrorBox error={stages.error} onRetry={() => stages.refetch()} />}
      {stages.isSuccess && items.length === 0 && (
        <Empty
          icon="rules"
          title="У объекта нет графика"
          action={
            <ButtonLink to={`/objects/${objectId}/settings`} variant="primary" icon="gantt">
              Построить график
            </ButtonLink>
          }
        >
          Правила приходят вместе с этапами — из шаблона при генерации по нормам МРР или импорте файла.
        </Empty>
      )}
      {stage && (
        <div className="grid items-start gap-5 lg:grid-cols-[21rem_minmax(0,1fr)]">
          <StageList items={items} current={stage} onSelect={select} />
          {/* Ключ — этап, а не версия правила: после сохранения итог пересчёта остаётся на экране. */}
          <RuleEditor key={stage.id} objectId={objectId} stage={stage} />
        </div>
      )}
    </div>
  );
}

function StageList({
  items,
  current,
  onSelect,
}: {
  items: StageRead[];
  current: StageRead;
  onSelect: (stage: StageRead) => void;
}) {
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();
  const shown = items.filter((s) => !needle || `${s.code} ${s.name}`.toLowerCase().includes(needle));
  return (
    <div className="rounded-2xl bg-white shadow-sm ring-1 ring-ink/[0.07] lg:sticky lg:top-20 lg:max-h-[calc(100vh-6.5rem)] lg:overflow-y-auto">
      <div className="sticky top-0 z-10 border-b border-ink/[0.07] bg-white p-2.5">
        <div className="relative">
          <Icon name="search" size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Найти этап" className={`${fieldClass("input", "sm")} pl-9`} />
        </div>
      </div>
      <ul className="p-2">
        {shown.map((stage) => {
          const active = stage.id === current.id;
          const state = !stage.rule ? "нет правила" : stage.rule.is_active ? `v${stage.rule.version}` : "выключено";
          return (
            <li key={stage.id}>
              <button
                type="button"
                onClick={() => onSelect(stage)}
                className={`block w-full rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                  active ? "bg-accent/[0.07] ring-1 ring-accent/40" : "hover:bg-canvas/70"
                }`}
              >
                <span className="flex items-center gap-2">
                  <Dot className={!stage.rule ? "bg-amber-400" : stage.rule.is_active ? "bg-emerald-500" : "bg-stone-400"} />
                  <span className="min-w-0 flex-1 truncate">
                    <span className="font-medium text-muted">{stage.code}</span> {stage.name}
                  </span>
                  <span className="shrink-0 text-[11px] text-muted">{state}</span>
                </span>
                <span className="mt-0.5 block pl-4 text-xs text-muted">
                  {formatPlanDate(stage.plan_start)} — {formatPlanDate(stage.plan_end)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function RuleEditor({ objectId, stage }: { objectId: string; stage: StageRead }) {
  const saved = stage.rule ? fromRule(stage.rule) : EMPTY_DRAFT;
  const [draft, dispatch] = useReducer(reduce, saved);
  const classes = useQuery(equipmentClassesQuery);
  const save = useSaveRule(objectId, stage);
  const names = (code: string) => classes.data?.get(code) ?? code;
  const options = [...(classes.data?.keys() ?? [])].filter((c) => c !== NOT_EQUIPMENT);
  const issues = problems(draft);
  const changed = !sameDraft(draft, saved);

  return (
    <article className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-ink/[0.07]">
      <header className="flex flex-wrap items-start gap-3 border-b border-ink/[0.07] px-6 py-4">
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold">
            <span className="text-muted">{stage.code}</span> {stage.name}
          </h2>
          <p className="text-sm text-muted">
            По плану {formatPlanDate(stage.plan_start)} — {formatPlanDate(stage.plan_end)} · участок «
            {isZoneType(stage.zone_type) ? ru.zoneType[stage.zone_type] : stage.zone_type}»
            {stage.rule && ` · правило версии ${stage.rule.version}`}
          </p>
        </div>
        <Toggle checked={draft.is_active} onChange={(value) => dispatch({ type: "active", value })} label="правило включено" />
      </header>

      {!stage.rule && (
        <p className="flex gap-2.5 border-b border-amber-200 bg-amber-50 px-6 py-3 text-sm text-amber-900">
          <Icon name="alert" size={16} className="mt-0.5 shrink-0" />
          У этапа нет правила: по нему не проверяются D1, D2, D8, D9, прогресс идёт по плану. Заполните
          правило и сохраните — оно появится.
        </p>
      )}

      <div className="space-y-7 p-6">
        <Section
          title="Обязательная техника"
          hint="Группа выполнена, если классов из неё в сумме не меньше минимума. Все группы — комплект этапа: нет ни одной — D1, часть — D2."
        >
          {draft.required.length === 0 && <p className="text-sm text-muted">Групп нет.</p>}
          <div className="space-y-2">
            {draft.required.map((group, index) => (
              <div key={index} className="flex flex-wrap items-center gap-2 rounded-xl bg-canvas/50 p-3 ring-1 ring-ink/[0.06]">
                <span className="text-sm text-muted">Любой из</span>
                <Chips
                  codes={group.any_of}
                  names={names}
                  options={options}
                  onAdd={(code) => dispatch({ type: "groupAdd", index, code })}
                  onRemove={(code) => dispatch({ type: "groupRemove", index, code })}
                />
                <label className="flex items-center gap-1.5 text-sm">
                  не меньше
                  <input
                    type="number"
                    min={1}
                    value={group.min}
                    onChange={(e) => dispatch({ type: "groupMin", index, min: Number(e.target.value) })}
                    className={`${fieldClass("input", "sm", "w-16")} tabular-nums`}
                  />
                </label>
                <button
                  type="button"
                  onClick={() => dispatch({ type: "removeGroup", index })}
                  className="ml-auto inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-red-700 hover:bg-red-50"
                >
                  <Icon name="trash" size={13} />
                  убрать группу
                </button>
              </div>
            ))}
          </div>
          <Button size="sm" variant="ghost" icon="plus" className="mt-2 -ml-2.5" onClick={() => dispatch({ type: "addGroup" })}>
            Группа
          </Button>
        </Section>

        <Section title="Допустимая техника" hint="Её присутствие на участке этапа не вызывает D3 «техника не по этапу».">
          <Chips
            codes={draft.allowed}
            names={names}
            options={options}
            onAdd={(code) => dispatch({ type: "allowedAdd", code })}
            onRemove={(code) => dispatch({ type: "allowedRemove", code })}
          />
        </Section>

        <Section
          title="Сигнатура старта"
          hint="Этап считается начатым, когда эти классы видны одновременно, а стадия по фото — не раньше указанной."
        >
          <div className="flex flex-wrap items-center gap-3">
            <Chips
              codes={draft.signature.equipment}
              names={names}
              options={options}
              onAdd={(code) => dispatch({ type: "signatureAdd", code })}
              onRemove={(code) => dispatch({ type: "signatureRemove", code })}
            />
            <label className="flex items-center gap-2 text-sm">
              стадия по фото
              <select
                value={draft.signature.stage_label ?? ""}
                onChange={(e) => dispatch({ type: "stageLabel", label: (e.target.value || null) as StageLabel | null })}
                className={fieldClass("select", "sm", "w-auto")}
              >
                <option value="">не важна</option>
                {STAGE_LABELS.map((l) => (
                  <option key={l} value={l}>
                    {ru.stageLabel[l]}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </Section>

        <Section title="Устойчивость" hint="Условие должно держаться столько рабочих сессий подряд: одиночный кадр не повод для тревоги.">
          <label className="flex items-center gap-2 text-sm">
            сессий подряд
            <input
              type="number"
              min={1}
              value={draft.min_sessions}
              onChange={(e) => dispatch({ type: "minSessions", value: Number(e.target.value) })}
              className={`${fieldClass("input", "sm", "w-16")} tabular-nums`}
            />
          </label>
        </Section>
      </div>

      <SaveBar draft={draft} saved={saved} changed={changed} issues={issues} dispatch={dispatch} save={save} objectId={objectId} stage={stage} />
    </article>
  );
}

function SaveBar({
  draft,
  saved,
  changed,
  issues,
  dispatch,
  save,
  objectId,
  stage,
}: {
  draft: RuleDraft;
  saved: RuleDraft;
  changed: boolean;
  issues: string[];
  dispatch: (action: Action) => void;
  save: ReturnType<typeof useSaveRule>;
  objectId: string;
  stage: StageRead;
}) {
  const remove = useDeleteRule(objectId, stage);
  const confirm = useConfirm();
  const toast = useToast();

  const onDelete = async () => {
    const ok = await confirm({
      title: `Удалить правило этапа «${stage.name}»?`,
      message: "По этапу перестанут проверяться D1, D2, D8, D9, прогресс пойдёт по плану. Лента пересчитается сразу.",
      confirmLabel: "Удалить правило",
      tone: "danger",
    });
    if (ok)
      remove.mutate(undefined, {
        onSuccess: () => toast.success("Правило удалено", "Лента пересчитана"),
        onError: (error) => toast.error(error, "Правило не удалено"),
      });
  };

  return (
    <div className="space-y-3 border-t border-ink/[0.07] bg-stone-50/70 px-6 py-4">
      {issues.map((issue) => (
        <p key={issue} className="flex items-center gap-2 text-sm text-red-700">
          <Icon name="alert" size={15} />
          {issue}
        </p>
      ))}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          icon="check"
          disabled={!changed || issues.length > 0}
          loading={save.isPending}
          onClick={() =>
            save.mutate(draft, {
              onSuccess: (result) => {
                dispatch({ type: "reset", draft: fromRule(result.rule) });
                toast.success(`Правило сохранено, версия ${result.rule.version}`, "Лента пересчитана — итог ниже");
              },
              onError: (error) => toast.error(error, "Правило не сохранено"),
            })
          }
        >
          {save.isPending ? "Сохраняем и пересчитываем…" : stage.rule ? "Сохранить и пересчитать" : "Создать правило и пересчитать"}
        </Button>
        <Button variant="ghost" disabled={!changed || save.isPending} onClick={() => dispatch({ type: "reset", draft: saved })}>
          Отменить правки
        </Button>
        {stage.rule && (
          <Button variant="ghost" icon="trash" className="ml-auto !text-red-700 hover:!bg-red-50" loading={remove.isPending} onClick={onDelete}>
            Удалить правило
          </Button>
        )}
      </div>
      {save.data && <SaveOutcome result={save.data} objectId={objectId} />}
      {remove.data && <FeedChange gone={remove.data.gone} added={remove.data.added} objectId={objectId} head="Правило удалено. Лента пересчитана." />}
    </div>
  );
}

/** Итог сохранения: что пересчёт сделал с лентой. Ради этого экрана и показывают демо. */
function SaveOutcome({ result, objectId }: { result: SaveResult; objectId: string }) {
  return (
    <FeedChange
      gone={result.gone}
      added={result.added}
      objectId={objectId}
      head={`Правило сохранено, версия ${result.rule.version}. Лента пересчитана.`}
    />
  );
}

function FeedChange({ gone, added, objectId, head }: { gone: DeviationRead[]; added: DeviationRead[]; objectId: string; head: string }) {
  const line = (d: DeviationRead) => `${d.code} — ${d.title}`;
  return (
    <div className="space-y-2 rounded-xl bg-emerald-50 p-4 text-sm text-emerald-950 ring-1 ring-emerald-200">
      <p className="font-medium">{head}</p>
      {gone.length === 0 && added.length === 0 && <p>Отклонения не изменились.</p>}
      {gone.length > 0 && (
        <div>
          <p className="flex items-center gap-1.5 font-medium">
            <Icon name="check" size={14} /> Исчезли из ленты — по новому правилу их не было:
          </p>
          <ul className="mt-0.5 list-disc pl-6">
            {gone.map((d) => (
              <li key={d.id}>{line(d)}</li>
            ))}
          </ul>
        </div>
      )}
      {added.length > 0 && (
        <div>
          <p className="flex items-center gap-1.5 font-medium">
            <Icon name="alert" size={14} /> Появились:
          </p>
          <ul className="mt-0.5 list-disc pl-6">
            {added.map((d) => (
              <li key={d.id}>{line(d)}</li>
            ))}
          </ul>
        </div>
      )}
      <Link to={`/objects/${objectId}/deviations?status=all`} className="inline-flex items-center gap-1 font-medium text-accent hover:underline">
        Открыть ленту предупреждений <Icon name="arrowRight" size={14} />
      </Link>
    </div>
  );
}

/** Классы техники списком с крестиками и выпадающим списком для добавления. */
function Chips({
  codes,
  names,
  options,
  onAdd,
  onRemove,
}: {
  codes: string[];
  names: (code: string) => string;
  options: string[];
  onAdd: (code: string) => void;
  onRemove: (code: string) => void;
}) {
  const free = options.filter((c) => !codes.includes(c));
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {codes.map((code) => (
        <span key={code} className="inline-flex h-7 items-center gap-1 rounded-lg bg-white pl-2.5 pr-1 text-sm shadow-sm ring-1 ring-ink/15">
          {names(code)}
          <button
            type="button"
            onClick={() => onRemove(code)}
            aria-label={`Убрать ${names(code)}`}
            className="flex h-5 w-5 items-center justify-center rounded text-muted hover:bg-red-50 hover:text-red-700"
          >
            <Icon name="x" size={12} />
          </button>
        </span>
      ))}
      {codes.length === 0 && <span className="text-sm text-muted">нет</span>}
      {free.length > 0 && (
        <select
          value=""
          onChange={(e) => e.target.value && onAdd(e.target.value)}
          className="h-7 max-w-40 rounded-lg border border-dashed border-accent/50 bg-transparent px-2 text-sm font-medium text-accent hover:bg-accent/[0.05] focus:outline-none focus:ring-2 focus:ring-accent"
        >
          <option value="">+ класс</option>
          {free.map((c) => (
            <option key={c} value={c}>
              {names(c)}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="font-semibold">{title}</h3>
      {hint && <p className="mb-2.5 mt-0.5 text-xs text-muted">{hint}</p>}
      {children}
    </section>
  );
}

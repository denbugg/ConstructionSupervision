import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { formatDelay, formatMoment, formatPlanDate } from "@/entities/format";
import { SEVERITY_ORDER, objectStatusTone, severityDot } from "@/entities/status";
import { CreateObjectDialog, EditObjectDialog } from "@/features/objects/ObjectFormDialog";
import { useObjectActions } from "@/features/objects/useObjectActions";
import {
  inScope,
  summarize,
  useObjectRows,
  visibleRows,
  type ObjectRow,
  type Scope,
  type Sort,
} from "@/features/objects/useObjectRows";
import type { ObjectRead } from "@/shared/api/queries";
import { label, ru } from "@/shared/locale/ru";
import { Badge, Dot } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { fieldClass, inputClass } from "@/shared/ui/Field";
import { Icon } from "@/shared/ui/Icon";
import { Menu } from "@/shared/ui/Menu";
import { PageContainer, PageHeader, Panel, Segmented, Stat } from "@/shared/ui/Page";
import { Empty, ErrorBox, Loading, Spinner } from "@/shared/ui/QueryState";

/** Список объектов: с какого объекта начать день — проблемные сверху, действия под рукой. */
export function ObjectsScreen() {
  const { objects, rows } = useObjectRows();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<ObjectRead | null>(null);
  const [scope, setScope] = useState<Scope>("current");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort>("attention");
  const shown = visibleRows(rows, scope, query, sort);
  const summary = summarize(rows);
  const count = (s: Scope) => rows.filter((row) => inScope(row, s)).length;

  return (
    <PageContainer>
      <PageHeader
        title="Объекты"
        description="Стройки под наблюдением: отставание от графика и открытые предупреждения по каждой."
        actions={
          <Button variant="primary" icon="plus" onClick={() => setCreating(true)}>
            Новый объект
          </Button>
        }
      />

      {objects.isPending && <Loading />}
      {objects.isError && <ErrorBox error={objects.error} onRetry={() => objects.refetch()} />}
      {objects.isSuccess && rows.length === 0 && (
        <Empty
          icon="building"
          title="Объектов пока нет"
          action={
            <Button variant="primary" icon="plus" onClick={() => setCreating(true)}>
              Создать первый объект
            </Button>
          }
        >
          Заведите объект, постройте график по нормам или из файла и загрузите снимки камер — система
          сама найдёт отставания и нарушения.
        </Empty>
      )}

      {rows.length > 0 && (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryTile icon="building" label="Действующих объектов" value={summary.current} />
            <SummaryTile
              icon="clock"
              label="С отставанием от графика"
              value={summary.delayed}
              tone={summary.delayed > 0 ? "text-red-700" : ""}
            />
            <SummaryTile
              icon="alert"
              label="Открытых предупреждений"
              value={summary.open}
              hint={summary.high > 0 ? `из них высокой серьёзности: ${summary.high}` : "высокой серьёзности нет"}
              tone={summary.high > 0 ? "text-red-700" : ""}
            />
            <SummaryTile
              icon="info"
              label="Ещё без анализа"
              value={summary.notAnalyzed}
              hint="нет снимков или графика"
            />
          </div>

          <Panel bodyClassName="">
            <div className="flex flex-wrap items-center gap-3 border-b border-ink/[0.07] px-5 py-3">
              <div className="relative w-full max-w-xs">
                <Icon name="search" size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Поиск по названию или адресу"
                  className={`${inputClass} pl-9`}
                />
              </div>
              <Segmented
                value={scope}
                onChange={setScope}
                options={[
                  { value: "current", label: "Действующие", count: count("current") },
                  { value: "archived", label: "Архив", count: count("archived") },
                  { value: "all", label: "Все", count: rows.length },
                ]}
              />
              <label className="ml-auto flex items-center gap-2 text-sm text-muted">
                Порядок
                <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} className={fieldClass("select", "md", "w-auto")}>
                  <option value="attention">сначала проблемные</option>
                  <option value="name">по названию</option>
                  <option value="start">по началу СМР</option>
                </select>
              </label>
            </div>
            {shown.length === 0 ? (
              <div className="p-5">
                <Empty icon="search" title="Ничего не найдено">
                  {query ? "Под поиск не попал ни один объект." : "В этом разделе объектов нет."}{" "}
                  <button type="button" onClick={() => { setQuery(""); setScope("all"); }} className="font-medium text-accent underline">
                    Показать все
                  </button>
                </Empty>
              </div>
            ) : (
              <ObjectTable rows={shown} onEdit={setEditing} />
            )}
          </Panel>
        </div>
      )}

      <CreateObjectDialog open={creating} onClose={() => setCreating(false)} />
      {editing && <EditObjectDialog object={editing} open onClose={() => setEditing(null)} />}
    </PageContainer>
  );
}

function SummaryTile({
  icon,
  label: title,
  value,
  hint,
  tone = "",
}: {
  icon: "building" | "clock" | "alert" | "info";
  label: string;
  value: number;
  hint?: string;
  tone?: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-ink/[0.07]">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-canvas text-muted">
        <Icon name={icon} size={18} />
      </span>
      <Stat label={title} value={value} hint={hint} tone={tone} />
    </div>
  );
}

function ObjectTable({ rows, onEdit }: { rows: ObjectRow[]; onEdit: (object: ObjectRead) => void }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] border-collapse text-left text-sm">
        <thead className="text-xs uppercase tracking-wide text-muted">
          <tr className="border-b border-ink/[0.07]">
            <th className="px-5 py-2.5 font-medium">Объект</th>
            <th className="whitespace-nowrap px-3 py-2.5 font-medium">По графику</th>
            <th className="whitespace-nowrap px-3 py-2.5 font-medium">Отставание</th>
            <th className="whitespace-nowrap px-3 py-2.5 font-medium">Предупреждения</th>
            <th className="whitespace-nowrap px-3 py-2.5 font-medium">Начало СМР</th>
            <th className="whitespace-nowrap px-3 py-2.5 font-medium">Анализ на</th>
            <th className="w-24 px-5 py-2.5" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <ObjectLine key={row.object.id} row={row} onEdit={onEdit} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ObjectLine({ row, onEdit }: { row: ObjectRow; onEdit: (object: ObjectRead) => void }) {
  const { object, status } = row;
  const navigate = useNavigate();
  const actions = useObjectActions();
  const archived = object.status === "ARCHIVED";
  const base = `/objects/${object.id}`;
  return (
    <tr
      onClick={() => navigate(base)}
      className={`group cursor-pointer border-b border-ink/[0.06] last:border-0 hover:bg-canvas/60 ${archived ? "text-ink/55" : ""}`}
    >
      <td className="max-w-md px-5 py-3.5">
        <Link to={base} onClick={(e) => e.stopPropagation()} className="font-medium text-ink group-hover:text-accent">
          {object.name}
        </Link>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
          <span>{label(ru.objectType, object.object_type)}</span>
          <span>·</span>
          <span>{label(ru.objectLifecycle, object.status)}</span>
          {object.address && (
            <>
              <span>·</span>
              <span className="truncate">{object.address}</span>
            </>
          )}
        </div>
      </td>
      <td className="px-3 py-3.5">
        {status === undefined && row.statusError == null && <Spinner className="text-muted" />}
        {row.statusError != null && <span className="text-red-700">статус не получен</span>}
        {status === null && <span className="text-muted">анализа не было</span>}
        {status && <Badge tone={objectStatusTone(status.status)}>{label(ru.objectStatus, status.status)}</Badge>}
      </td>
      <td className={`whitespace-nowrap px-3 py-3.5 tabular-nums ${status?.delay_days && status.delay_days > 0 ? "font-medium text-red-700" : ""}`}>
        {status?.delay_days != null ? `${formatDelay(status.delay_days)} ${ru.units.workDays}` : "—"}
      </td>
      <td className="px-3 py-3.5">
        {status ? <SeverityCounts counts={status.deviations} /> : "—"}
      </td>
      <td className="whitespace-nowrap px-3 py-3.5 tabular-nums">{formatPlanDate(object.plan_start)}</td>
      <td className="whitespace-nowrap px-3 py-3.5 text-muted tabular-nums">{status ? formatMoment(status.as_of) : "—"}</td>
      <td className="px-5 py-3.5">
        <div className="flex items-center justify-end gap-1">
          <Icon name="arrowRight" size={16} className="text-muted opacity-0 transition group-hover:opacity-100" />
          <Menu
            size="sm"
            items={[
              { label: "Открыть", icon: "home", onSelect: () => navigate(base) },
              { label: "Предупреждения", icon: "alert", onSelect: () => navigate(`${base}/deviations`) },
              { label: "График", icon: "gantt", onSelect: () => navigate(`${base}/gantt`) },
              { label: "Загрузить снимки", icon: "upload", onSelect: () => navigate(`${base}/upload`) },
              "divider",
              { label: "Редактировать реквизиты", icon: "edit", onSelect: () => onEdit(object) },
              archived
                ? { label: "Вернуть из архива", icon: "restore", onSelect: () => actions.restore(object) }
                : { label: "В архив", icon: "archive", tone: "danger", onSelect: () => actions.archive(object) },
            ]}
          />
        </div>
      </td>
    </tr>
  );
}

/** Открытые отклонения точками по серьёзности: сразу видно, есть ли высокие. */
function SeverityCounts({ counts }: { counts: Record<string, number> }) {
  const present = SEVERITY_ORDER.filter((s) => (counts[s] ?? 0) > 0);
  if (present.length === 0) return <span className="text-muted">нет</span>;
  return (
    <span className="flex flex-wrap items-center gap-2.5">
      {present.map((s) => (
        <span key={s} className="inline-flex items-center gap-1 tabular-nums" title={label(ru.severity, s)}>
          <Dot className={severityDot(s)} />
          {counts[s]}
        </span>
      ))}
    </span>
  );
}

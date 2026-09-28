import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { splitRefs } from "@/entities/deviation";
import { formatMoment, formatPlanDate, formatSize } from "@/entities/format";
import {
  PERIOD_PRESETS,
  type Period,
  type ReportCreated,
  defaultPeriod,
  periodProblem,
  useCreateReport,
  useDeviationRefs,
  useReports,
  useSummary,
} from "@/features/reports/useReports";
import { label, ru } from "@/shared/locale/ru";
import { Button, buttonClass } from "@/shared/ui/Button";
import { Field, fieldClass } from "@/shared/ui/Field";
import { Icon } from "@/shared/ui/Icon";
import { PageHeader, Panel } from "@/shared/ui/Page";
import { Empty, ErrorBox, Loading } from "@/shared/ui/QueryState";
import { useToast } from "@/shared/ui/Toast";

/**
 * Отчёты объекта: сформировать PDF за период и открыть готовые (apps/web/README.md, §3).
 * Отчёт оформляет выводы последнего анализа, поэтому без анализа формировать нечего.
 */
export function ReportsScreen() {
  const { objectId = "" } = useParams();
  const { status, reports } = useReports(objectId);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Отчёты"
        description="PDF план-факт: статус и SPI, Гант, загрузка техники, отклонения со снимками-доказательствами, резюме и раздел «Ограничения» — чего система за период не видела."
      />

      {status.isPending && <Loading />}
      {status.isError && <ErrorBox error={status.error} onRetry={() => status.refetch()} />}
      {status.data === null && (
        <Empty icon="report" title="Формировать пока нечего">
          Отчёт оформляет выводы анализа, а анализа по объекту ещё не было. Он запускается сам после
          распознавания снимков; вручную — кнопкой «Пересчитать» вверху.
        </Empty>
      )}
      {status.data && (
        // Новый анализ — новый период по умолчанию.
        <CreateForm key={status.data.as_of} objectId={objectId} asOf={status.data.as_of} />
      )}

      <Panel title="Сформированные отчёты" icon="folder" bodyClassName="">
        {reports.isPending && <div className="px-5"><Loading /></div>}
        {reports.isError && <div className="p-5"><ErrorBox error={reports.error} onRetry={() => reports.refetch()} /></div>}
        {reports.data?.total === 0 && <p className="px-5 py-6 text-sm text-muted">Отчётов по объекту ещё нет — сформируйте первый формой выше.</p>}
        {reports.data && reports.data.total > 0 && (
          <ul className="divide-y divide-ink/[0.06]">
            {reports.data.items.map((report) => (
              <li key={report.key} className="flex flex-wrap items-center gap-4 px-5 py-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-red-50 text-red-700">
                  <Icon name="report" size={19} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium tabular-nums">
                    {formatPlanDate(report.period_from)} — {formatPlanDate(report.period_to)}
                  </p>
                  <p className="text-xs text-muted">
                    сформирован {formatMoment(report.created_at)} · {formatSize(report.size_bytes)}
                  </p>
                </div>
                <a href={report.url} target="_blank" rel="noreferrer" className={buttonClass("secondary", "sm")}>
                  <Icon name="external" size={15} />
                  Открыть
                </a>
                <a href={report.url} download className={buttonClass("ghost", "sm")}>
                  <Icon name="download" size={15} />
                  Скачать
                </a>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function CreateForm({ objectId, asOf }: { objectId: string; asOf: string }) {
  const [period, setPeriod] = useState<Period>(() => defaultPeriod(asOf));
  const create = useCreateReport(objectId);
  const summary = useSummary(objectId);
  const toast = useToast();
  const problem = periodProblem(period);

  const submit = () => {
    if (problem) return;
    create.mutate(period, {
      onSuccess: (report) => toast.success("Отчёт готов", `${formatPlanDate(report.period_from)} — ${formatPlanDate(report.period_to)}`),
      onError: (error) => toast.error(error, "Отчёт не сформирован"),
    });
  };

  return (
    <Panel title="Новый отчёт" icon="report" bodyClassName="p-5 space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-wrap gap-1">
          {PERIOD_PRESETS.map((preset) => {
            const value = defaultPeriod(asOf, preset.days);
            const active = value.from === period.from && value.to === period.to;
            return (
              <button
                key={preset.label}
                type="button"
                onClick={() => setPeriod(value)}
                className={`h-9 rounded-lg px-3 text-sm font-medium ${active ? "bg-ink text-white" : "text-ink/70 ring-1 ring-ink/15 hover:bg-ink/[0.04]"}`}
              >
                {preset.label}
              </button>
            );
          })}
        </div>
        <Field label="С">
          <input type="date" value={period.from} onChange={(e) => setPeriod({ ...period, from: e.target.value })} className={fieldClass("input", "md", "w-auto")} />
        </Field>
        <Field label="По (включительно)">
          <input type="date" value={period.to} onChange={(e) => setPeriod({ ...period, to: e.target.value })} className={fieldClass("input", "md", "w-auto")} />
        </Field>
        <div className="ml-auto flex flex-wrap gap-2">
          <Button icon="sparkle" loading={summary.isPending} disabled={problem != null} onClick={() => summary.mutate(period)}>
            Резюме за период
          </Button>
          <Button variant="primary" icon="report" loading={create.isPending} disabled={problem != null} onClick={submit}>
            {create.isPending ? "Формируем PDF…" : "Сформировать PDF"}
          </Button>
        </div>
      </div>
      <p className="text-xs text-muted">
        Даты — сутки по Москве. Выводы — на момент анализа {formatMoment(asOf)}; дни периода позже
        него отчёт назовёт в «Ограничениях». Каждый сформированный отчёт сохраняется отдельно.
      </p>
      {problem && <p className="text-sm text-red-700">{problem}</p>}
      {create.isError && <ErrorBox error={create.error} />}
      {create.data && <Created report={create.data} />}
      {summary.isError && <ErrorBox error={summary.error} />}
      {summary.data && (
        <div className="space-y-2 rounded-xl bg-canvas/60 p-4 text-sm ring-1 ring-ink/[0.06]">
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <Icon name="sparkle" size={14} />
            Резюме за {formatPlanDate(summary.data.period_from)} — {formatPlanDate(summary.data.period_to)} ·
            источник: {label(ru.summarySource, summary.data.generated_by)}
          </p>
          <SummaryText objectId={objectId} text={summary.data.text} />
          {summary.data.llm_rejected.length > 0 && (
            <p className="text-xs text-muted">Текст нейросети отброшен: {summary.data.llm_rejected.join("; ")}</p>
          )}
        </div>
      )}
    </Panel>
  );
}

/** Текст резюме: ссылки на отклонения (`[bac02fc0]`) открывают их карточки в ленте. */
function SummaryText({ objectId, text }: { objectId: string; text: string }) {
  const refs = useDeviationRefs(objectId);
  return (
    <p className="whitespace-pre-line leading-relaxed">
      {splitRefs(text).map((part, i) => {
        const id = part.ref ? refs.get(part.text) : undefined;
        return id ? (
          <Link
            key={i}
            to={`/objects/${objectId}/deviations?status=all&id=${id}`}
            title="Открыть карточку отклонения"
            className="font-medium text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
          >
            {part.text}
          </Link>
        ) : (
          <span key={i}>{part.text}</span>
        );
      })}
    </p>
  );
}

function Created({ report }: { report: ReportCreated }) {
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-xl bg-emerald-50 p-4 text-sm text-emerald-950 ring-1 ring-emerald-200">
      <Icon name="check" size={18} className="text-emerald-700" />
      <div className="min-w-0 flex-1">
        <p className="font-medium">
          Отчёт за {formatPlanDate(report.period_from)} — {formatPlanDate(report.period_to)} готов ({formatSize(report.size_bytes)})
        </p>
        <p className="text-emerald-900/80">
          Снимков-доказательств: {report.evidence_images}
          {report.evidence_missing > 0 && `, не вставлено: ${report.evidence_missing} — причины в разделе «Ограничения»`}.
          Резюме: {label(ru.summarySource, report.summary_generated_by)}.
        </p>
      </div>
      <a href={report.url} target="_blank" rel="noreferrer" className={buttonClass("primary", "md")}>
        <Icon name="external" size={16} />
        Открыть PDF
      </a>
    </div>
  );
}

import { Link, useParams } from "react-router-dom";

import { formatDelay, formatMoment, formatPlanDate, formatSpi } from "@/entities/format";
import { SEVERITY_ORDER, objectStatusText, openDeviations, severityDot } from "@/entities/status";
import {
  ActiveStagesPanel,
  AttentionPanel,
  LatestImagesPanel,
  SetupChecklist,
  StagesPanel,
} from "@/features/dashboard/DashboardPanels";
import { useDashboard } from "@/features/dashboard/useDashboard";
import type { ObjectStatus } from "@/shared/api/queries";
import { label, ru } from "@/shared/locale/ru";
import { Dot } from "@/shared/ui/Badge";
import { ButtonLink } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { PageHeader, Panel, Stat } from "@/shared/ui/Page";
import { ErrorBox, Loading } from "@/shared/ui/QueryState";

/**
 * Обзор объекта: что не так и насколько можно верить выводу. Каждое число подписано,
 * откуда оно; прогноз — с уверенностью и оговоркой о темпе (apps/web/README.md, §5).
 */
export function DashboardScreen() {
  const { objectId = "" } = useParams();
  const { object, status } = useDashboard(objectId);

  if (!object.data) return null;
  const o = object.data;

  return (
    <div className="space-y-5">
      <PageHeader
        title={o.name}
        description={[
          label(ru.objectType, o.object_type),
          o.address,
          o.plan_start && `начало СМР ${formatPlanDate(o.plan_start)}`,
          `версия плана ${o.plan_version}`,
        ]
          .filter(Boolean)
          .join(" · ")}
      />

      <SetupChecklist object={o} />

      {status.isPending && <Loading />}
      {status.isError && <ErrorBox error={status.error} onRetry={() => status.refetch()} />}
      {/* Анализа не было — об этом и о кнопке запуска говорит чек-лист подготовки выше. */}
      {status.data && <StatusOverview objectId={objectId} status={status.data} />}

      <ActiveStagesPanel objectId={objectId} />
      <LatestImagesPanel objectId={objectId} />
    </div>
  );
}

function StatusOverview({ objectId, status }: { objectId: string; status: ObjectStatus }) {
  const facts = status.facts as Record<string, unknown>;
  const visible = typeof facts.visible_share === "number" ? `${Math.round(facts.visible_share * 100)} %` : "—";
  return (
    <>
      <div className="grid gap-5 lg:grid-cols-3">
        <Panel className="lg:col-span-2" bodyClassName="p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-[13px] text-muted">Статус по графику</p>
              <p className={`mt-1 text-3xl font-semibold tracking-tight ${objectStatusText(status.status)}`}>
                {label(ru.objectStatus, status.status)}
                {status.delay_days != null && status.delay_days !== 0 && (
                  <span className="ml-2 tabular-nums">
                    {formatDelay(status.delay_days)} {ru.units.workDays}
                  </span>
                )}
              </p>
              <p className="mt-1 max-w-xl text-sm text-muted">
                {status.delay_days != null
                  ? "Отставание по критическому пути при сохранении текущего темпа."
                  : "Отставание не оценено: мало наблюдений или участки не видны."}
                {status.status === "UNKNOWN" &&
                  typeof facts.min_days_for_forecast === "number" &&
                  ` Для прогноза нужно не меньше ${facts.min_days_for_forecast} дней наблюдений.`}
              </p>
            </div>
            <div className="text-right text-xs text-muted">
              <p className="flex items-center justify-end gap-1.5">
                <Icon name="clock" size={13} />
                на {formatMoment(status.as_of)}
              </p>
              <p>посчитано {formatMoment(status.computed_at)}</p>
            </div>
          </div>
          <div className="mt-6 grid grid-cols-2 gap-5 border-t border-ink/[0.07] pt-5 sm:grid-cols-4">
            <Stat
              label="SPI"
              value={formatSpi(status.spi)}
              hint="освоено к плану; меньше 1 — отстаём"
              tone={status.spi != null && status.spi < 0.9 ? "text-red-700" : ""}
            />
            <Stat label="Уверенность" value={label(ru.confidence, status.confidence)} hint="по дням и видимости" />
            <Stat label="Дней наблюдений" value={String(facts.observation_days ?? "—")} hint="с распознанными снимками" />
            <Stat label="Видимость участков" value={visible} hint="доля видимых камерами" />
          </div>
        </Panel>
        <DeviationSummary objectId={objectId} counts={status.deviations} />
      </div>

      {status.blind_areas > 0 && (
        <div className="flex items-start gap-3 rounded-2xl bg-amber-50 p-4 text-amber-900 ring-1 ring-amber-200">
          <Icon name="eye" size={18} className="mt-0.5 shrink-0" />
          <div className="flex-1 text-sm">
            <p className="font-medium">Участков вне контроля ИИ: {status.blind_areas} — проверить вручную</p>
            <p>В последней рабочей сессии их не видела ни одна камера.</p>
          </div>
          <ButtonLink to={`/objects/${objectId}/deviations?code=D10`} size="sm">
            Какие участки
          </ButtonLink>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <AttentionPanel objectId={objectId} />
        <StagesPanel objectId={objectId} status={status} />
      </div>
    </>
  );
}

/** Открытые отклонения по серьёзности: каждая строка — ссылка в ленту с этим фильтром. */
function DeviationSummary({ objectId, counts }: { objectId: string; counts: Record<string, number> }) {
  const total = openDeviations(counts);
  const max = Math.max(1, ...SEVERITY_ORDER.map((s) => counts[s] ?? 0));
  const base = `/objects/${objectId}/deviations`;
  return (
    <Panel bodyClassName="p-6 flex h-full flex-col">
      <p className="text-[13px] text-muted">Открытые предупреждения</p>
      <p className={`mt-1 text-3xl font-semibold tabular-nums ${total > 0 ? "" : "text-emerald-700"}`}>{total}</p>
      <div className="mt-4 space-y-2">
        {SEVERITY_ORDER.map((severity) => {
          const n = counts[severity] ?? 0;
          return (
            <Link
              key={severity}
              to={`${base}?severity=${severity}`}
              className="group flex items-center gap-3 rounded-lg px-2 py-1 -mx-2 text-sm hover:bg-canvas/70"
            >
              <Dot className={severityDot(severity)} />
              <span className="w-20 shrink-0">{label(ru.severity, severity)}</span>
              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink/[0.06]">
                <span className={`block h-full rounded-full ${severityDot(severity)}`} style={{ width: `${(n / max) * 100}%` }} />
              </span>
              <span className="w-6 text-right font-medium tabular-nums">{n}</span>
            </Link>
          );
        })}
      </div>
      <div className="mt-auto pt-5">
        <ButtonLink to={base} variant={total > 0 ? "primary" : "secondary"} icon="alert" className="w-full">
          {total > 0 ? "Разобрать предупреждения" : "Открыть ленту"}
        </ButtonLink>
      </div>
    </Panel>
  );
}

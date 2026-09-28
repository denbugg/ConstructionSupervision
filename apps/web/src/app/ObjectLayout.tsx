import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Outlet, useNavigate, useParams } from "react-router-dom";

import { formatDelay, formatMoment } from "@/entities/format";
import { runSummary } from "@/entities/run";
import { objectStatusTone } from "@/entities/status";
import { useRecompute } from "@/features/dashboard/useDashboard";
import { planQuery } from "@/features/gantt/useGantt";
import { EditObjectDialog } from "@/features/objects/ObjectFormDialog";
import { PlanSetupDialog } from "@/features/objects/PlanSetupDialog";
import { useObjectActions } from "@/features/objects/useObjectActions";
import { objectQuery, statusQuery, type ObjectRead } from "@/shared/api/queries";
import { label, ru } from "@/shared/locale/ru";
import { Badge } from "@/shared/ui/Badge";
import { Button, ButtonLink } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { Menu } from "@/shared/ui/Menu";
import { PageContainer } from "@/shared/ui/Page";
import { ErrorBox, Loading } from "@/shared/ui/QueryState";
import { useToast } from "@/shared/ui/Toast";

/**
 * Рамка экранов объекта: закреплённая шапка с названием, статусом по графику и главными
 * действиями — пересчитать, загрузить снимки, править объект. Доступны с любого экрана.
 */
export function ObjectLayout() {
  const { objectId = "" } = useParams();
  const object = useQuery(objectQuery(objectId));

  if (object.isPending) {
    return (
      <PageContainer>
        <Loading />
      </PageContainer>
    );
  }
  if (object.isError) {
    return (
      <PageContainer>
        <div className="space-y-3">
          <ErrorBox error={object.error} onRetry={() => object.refetch()} />
          <Link to="/objects" className="text-sm font-medium text-accent underline">
            ← К списку объектов
          </Link>
        </div>
      </PageContainer>
    );
  }
  return (
    <>
      <ObjectBar object={object.data} />
      {object.data.status === "ARCHIVED" && <ArchivedBanner object={object.data} />}
      <PageContainer>
        <Outlet />
      </PageContainer>
    </>
  );
}

function ObjectBar({ object }: { object: ObjectRead }) {
  const status = useQuery(statusQuery(object.id));
  const plan = useQuery(planQuery(object.id));
  const recompute = useRecompute(object.id, status.data?.as_of);
  const actions = useObjectActions();
  const toast = useToast();
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [planning, setPlanning] = useState(false);
  const base = `/objects/${object.id}`;
  const archived = object.status === "ARCHIVED";

  const runAnalysis = () =>
    recompute.mutate(undefined, {
      onSuccess: (run) =>
        toast.success(`Анализ пересчитан на ${formatMoment(run.as_of)}`, runSummary(run.stats as Record<string, unknown>)),
      onError: (error) => toast.error(error, "Анализ не пересчитан"),
    });

  return (
    <header className="sticky top-14 z-20 border-b border-ink/10 bg-canvas/90 backdrop-blur lg:top-0">
      <div className="mx-auto flex min-h-14 max-w-[1480px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2 sm:px-6 lg:px-8">
        <nav className="flex min-w-0 flex-1 basis-56 items-center gap-1.5 text-sm" aria-label="Путь">
          <Link to="/objects" className="shrink-0 text-muted hover:text-ink">
            Объекты
          </Link>
          <Icon name="chevronRight" size={14} className="text-muted/60" />
          <Link to={base} className="truncate font-medium hover:text-accent" title={object.name}>
            {object.name}
          </Link>
          {status.data && (
            <span className="ml-2 hidden shrink-0 items-center gap-2 md:flex">
              <Badge tone={objectStatusTone(status.data.status)}>
                {label(ru.objectStatus, status.data.status)}
                {status.data.delay_days != null && status.data.delay_days !== 0 && (
                  <span className="tabular-nums">
                    · {formatDelay(status.data.delay_days)} {ru.units.workDays}
                  </span>
                )}
              </Badge>
              <span className="text-xs text-muted" title="Момент, на который посчитаны выводы">
                на {formatMoment(status.data.as_of)}
              </span>
            </span>
          )}
        </nav>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            icon="refresh"
            loading={recompute.isPending}
            onClick={runAnalysis}
            title="Прогнать анализ на тот же момент — увидеть, что изменили правки настроек"
          >
            <span className="hidden sm:inline">{recompute.isPending ? "Считаем…" : "Пересчитать"}</span>
          </Button>
          <ButtonLink to={`${base}/upload`} size="sm" variant="dark" icon="upload" title="Загрузить снимки">
            <span className="hidden sm:inline">Загрузить снимки</span>
          </ButtonLink>
          <Menu
            size="sm"
            variant="secondary"
            label="Действия с объектом"
            items={[
              { label: "Редактировать реквизиты", icon: "edit", onSelect: () => setEditing(true) },
              {
                label: (plan.data?.stages.length ?? 0) > 0 ? "Перестроить график" : "Построить график",
                icon: "gantt",
                hint: "по нормам МРР или из файла",
                onSelect: () => setPlanning(true),
              },
              { label: "Сформировать отчёт", icon: "report", onSelect: () => navigate(`${base}/reports`) },
              "divider",
              archived
                ? { label: "Вернуть из архива", icon: "restore", onSelect: () => actions.restore(object) }
                : {
                    label: "В архив",
                    icon: "archive",
                    tone: "danger",
                    onSelect: () => actions.archive(object, () => navigate("/objects")),
                  },
            ]}
          />
        </div>
      </div>
      {editing && <EditObjectDialog object={object} open onClose={() => setEditing(false)} />}
      {planning && (
        <PlanSetupDialog object={object} stages={plan.data?.stages.length ?? 0} open onClose={() => setPlanning(false)} />
      )}
    </header>
  );
}

function ArchivedBanner({ object }: { object: ObjectRead }) {
  const actions = useObjectActions();
  return (
    <div className="border-b border-amber-200 bg-amber-50 text-amber-900">
      <div className="mx-auto flex max-w-[1480px] flex-wrap items-center gap-3 px-4 py-2.5 text-sm sm:px-6 lg:px-8">
        <Icon name="archive" size={16} />
        <span className="flex-1">Объект в архиве: данные доступны для просмотра, в списке действующих его нет.</span>
        <Button size="sm" icon="restore" onClick={() => actions.restore(object)} loading={actions.busy}>
          Вернуть в работу
        </Button>
      </div>
    </div>
  );
}

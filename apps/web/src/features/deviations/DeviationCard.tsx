import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { factLines, groupRows, sessionRows } from "@/entities/deviation";
import { formatMoment } from "@/entities/format";
import { deviationStatusTone, severityTone } from "@/entities/status";
import { zoneColor } from "@/entities/zones";
import { zonePolygon } from "@/features/cameras/useCameras";
import { useExplain, useVerdict } from "@/features/deviations/useDeviations";
import {
  camerasQuery,
  equipmentClassesQuery,
  imageQuery,
  zonesQuery,
  type DeviationRead,
  type ExplainRead,
} from "@/shared/api/queries";
import { label, ru } from "@/shared/locale/ru";
import { Badge } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { textareaClass } from "@/shared/ui/Field";
import { Frame } from "@/shared/ui/Frame";
import { Icon } from "@/shared/ui/Icon";
import { DetectionBox, ZoneOutline } from "@/shared/ui/overlays";
import { ErrorBox, Loading } from "@/shared/ui/QueryState";
import { useToast } from "@/shared/ui/Toast";

const EVIDENCE_COLOR = "#c2451a";

/**
 * Карточка отклонения: что система решила, на каких числах, по какому правилу и на каком
 * снимке. Оператор должен за десять секунд понять, согласен ли он (methodology.md, раздел 12).
 */
export function DeviationCard({
  objectId,
  deviation,
  onVerdict,
}: {
  objectId: string;
  deviation: DeviationRead;
  /** Вердикт сохранён: экран переходит к следующей карточке. */
  onVerdict?: () => void;
}) {
  const explain = useExplain(deviation.id);
  const classes = useQuery(equipmentClassesQuery);
  const names = (code: string) => classes.data?.get(code) ?? code;
  const facts = deviation.facts as Record<string, unknown>;
  const groups = groupRows(facts, names);
  const lines = factLines(facts);

  return (
    <article className="animate-fade-in overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-ink/[0.07]">
      <header className="space-y-2.5 border-b border-ink/[0.07] p-6">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={severityTone(deviation.severity)}>
            {deviation.code} · {label(ru.severity, deviation.severity)}
          </Badge>
          <Badge tone={deviationStatusTone(deviation.status)}>{label(ru.deviationStatus, deviation.status)}</Badge>
          <span className="text-sm text-muted">{label(ru.deviationCode, deviation.code)}</span>
        </div>
        <h2 className="text-xl font-semibold leading-snug">{deviation.title}</h2>
        <p className="text-[15px] leading-relaxed text-ink/85">{deviation.message}</p>
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
          <span className="flex items-center gap-1.5">
            <Icon name="clock" size={14} />
            {formatMoment(deviation.first_seen_at)} — {formatMoment(deviation.last_seen_at)}
          </span>
          <span>рабочих сессий: {deviation.occurrences}</span>
        </p>
      </header>

      <Verdict deviation={deviation} onDone={onVerdict} />

      <div className="space-y-7 p-6">
        {(groups.length > 0 || lines.length > 0) && (
          <Section title="Числа" icon="gauge">
            {groups.length > 0 && (
              <div className="mb-4 overflow-hidden rounded-xl ring-1 ring-ink/[0.08]">
                <table className="w-full border-collapse text-left text-sm">
                  <thead className="bg-stone-50 text-xs text-muted">
                    <tr>
                      <th className="px-3 py-2 font-medium">Обязательная техника</th>
                      <th className="px-3 py-2 font-medium">Норма</th>
                      <th className="px-3 py-2 font-medium">Было</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groups.map((g) => (
                      <tr key={g.classes} className="border-t border-ink/[0.06]">
                        <td className="px-3 py-2">{g.classes}</td>
                        <td className="px-3 py-2 tabular-nums">не меньше {g.min}</td>
                        <td className={`px-3 py-2 font-semibold tabular-nums ${g.ok ? "text-emerald-700" : "text-red-700"}`}>
                          <span className="inline-flex items-center gap-1">
                            {g.observed}
                            <Icon name={g.ok ? "check" : "x"} size={14} />
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
              {lines.map((line) => (
                <div key={line.label} className="contents">
                  <dt className="text-muted">{line.label}</dt>
                  <dd>{line.value}</dd>
                </div>
              ))}
            </dl>
          </Section>
        )}

        {explain.isPending && <Loading />}
        {explain.isError && <ErrorBox error={explain.error} onRetry={() => explain.refetch()} />}
        {explain.data && (
          <>
            <EvidenceSection objectId={objectId} deviation={deviation} explain={explain.data} />
            <RuleSection objectId={objectId} explain={explain.data} facts={facts} />
            <SessionsSection deviation={deviation} explain={explain.data} names={names} />
          </>
        )}
      </div>
    </article>
  );
}

function Verdict({ deviation, onDone }: { deviation: DeviationRead; onDone?: () => void }) {
  const verdict = useVerdict(deviation);
  const toast = useToast();
  const [comment, setComment] = useState(deviation.verdict_comment ?? "");
  const [commenting, setCommenting] = useState(Boolean(deviation.verdict_comment));

  const send = (status: "CONFIRMED" | "REJECTED") =>
    verdict.mutate(
      { status, comment },
      {
        onSuccess: () => {
          toast.success(status === "CONFIRMED" ? "Нарушение подтверждено" : "Отмечено как ложное", deviation.title);
          onDone?.();
        },
        onError: (error) => toast.error(error, "Вердикт не сохранён"),
      },
    );

  return (
    <div className="space-y-3 bg-canvas/50 px-6 py-4">
      {deviation.verdict_at != null && (
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <Badge tone={deviationStatusTone(deviation.verdict ?? "RESOLVED")}>{label(ru.verdict, deviation.verdict)}</Badge>
          <span className="text-muted">
            {deviation.verdict_by ?? "оператор"}, {formatMoment(deviation.verdict_at)}
            {deviation.verdict_comment && ` — «${deviation.verdict_comment}»`}
          </span>
        </p>
      )}
      {deviation.status === "RESOLVED" && (
        <p className="text-sm text-muted">
          Отклонение закрыто: условие уже не выполняется. Вердикт останется в истории — «да, это
          было» или «ложное срабатывание».
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-sm font-medium">Ваш вердикт:</span>
        <Button variant="danger" icon="check" loading={verdict.isPending && verdict.variables?.status === "CONFIRMED"} disabled={verdict.isPending} onClick={() => send("CONFIRMED")}>
          Подтвердить
        </Button>
        <Button icon="x" loading={verdict.isPending && verdict.variables?.status === "REJECTED"} disabled={verdict.isPending} onClick={() => send("REJECTED")}>
          Ложное срабатывание
        </Button>
        {!commenting && (
          <Button variant="ghost" size="sm" icon="edit" onClick={() => setCommenting(true)}>
            Комментарий
          </Button>
        )}
      </div>
      {commenting && (
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Комментарий к вердикту: что видно на площадке, кто проверил"
          maxLength={2000}
          rows={2}
          className={textareaClass}
        />
      )}
    </div>
  );
}

function RuleSection({ objectId, explain, facts }: { objectId: string; explain: ExplainRead; facts: Record<string, unknown> }) {
  const rule = explain.rule;
  const stageVersion = typeof facts.stage_rule_version === "number" ? facts.stage_rule_version : null;
  // Пороги — числа и флаги; вложенные словари (шаблоны текстов, названия причин) оператору
  // здесь не нужны: их видно в самом тексте отклонения.
  const params = Object.entries(rule?.params ?? {}).filter(
    ([, value]) => value === null || typeof value !== "object",
  );
  return (
    <Section
      title="Правило"
      icon="rules"
      actions={
        <div className="flex gap-1">
          {stageVersion != null && explain.deviation.stage_id && (
            <Link to={`/objects/${objectId}/settings/rules?stage=${explain.deviation.stage_id}`} className="text-xs font-medium text-accent hover:underline">
              правило этапа →
            </Link>
          )}
          <Link to="/settings/deviation-rules" className="ml-3 text-xs font-medium text-accent hover:underline">
            пороги {rule?.code ?? ""} →
          </Link>
        </div>
      }
    >
      {rule == null ? (
        <p className="text-sm text-muted">Настройки правила не найдены.</p>
      ) : (
        <div className="space-y-2 text-sm">
          <p>
            {rule.code} «{label(ru.deviationCode, rule.code)}» · базовая серьёзность{" "}
            {label(ru.severity, rule.severity).toLowerCase()}
            {!rule.enabled && " · правило выключено"}
          </p>
          {params.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {params.map(([key, value]) => (
                <span key={key} className="rounded-md bg-ink/[0.05] px-2 py-0.5 text-xs">
                  {label(ru.ruleParam, key)}: <b className="tabular-nums">{String(value)}</b>
                </span>
              ))}
            </div>
          )}
          {stageVersion != null && (
            <p className="text-muted">Правило этапа «этап → техника», версия {stageVersion}: на нём построены нормы выше.</p>
          )}
        </div>
      )}
    </Section>
  );
}

/** Снимок-доказательство: рамки техники из вывода и зона участка отклонения. */
function EvidenceSection({
  objectId,
  deviation,
  explain,
}: {
  objectId: string;
  deviation: DeviationRead;
  explain: ExplainRead;
}) {
  const [index, setIndex] = useState(0);
  const evidence = explain.evidence;
  const current = evidence[Math.min(index, evidence.length - 1)];
  if (!current) {
    const reason = (deviation.facts as Record<string, unknown>).evidence_absent_reason;
    return (
      <Section title="Снимок" icon="image">
        <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
          Снимков нет{typeof reason === "string" ? `: ${reason}` : ""}. Участок не был виден — вывод
          «проверить вручную», а не «пусто».
        </p>
      </Section>
    );
  }
  return (
    <Section
      title={`Снимок-доказательство${evidence.length > 1 ? ` · ${index + 1} из ${evidence.length}` : ""}`}
      icon="image"
      actions={
        evidence.length > 1 && (
          <div className="flex items-center gap-1">
            {evidence.map((e, i) => (
              <button
                key={e.image_id}
                type="button"
                onClick={() => setIndex(i)}
                className={`h-7 min-w-7 rounded-md px-2 text-xs font-medium ${i === index ? "bg-ink text-white" : "text-ink/70 hover:bg-ink/[0.06]"}`}
              >
                {i + 1}
              </button>
            ))}
          </div>
        )
      }
    >
      <EvidenceFrame
        key={current.image_id}
        objectId={objectId}
        imageId={current.image_id}
        detectionIds={current.detection_ids}
        area={deviation.area ?? null}
      />
    </Section>
  );
}

function EvidenceFrame({
  objectId,
  imageId,
  detectionIds,
  area,
}: {
  objectId: string;
  imageId: string;
  detectionIds: string[];
  area: string | null;
}) {
  const image = useQuery(imageQuery(imageId));
  const cameraId = image.data?.camera_id ?? "";
  const zones = useQuery({ ...zonesQuery(cameraId), enabled: cameraId !== "" });
  const cameras = useQuery(camerasQuery(objectId));
  const classes = useQuery(equipmentClassesQuery);

  if (image.isPending) return <Loading />;
  if (image.isError) return <ErrorBox error={image.error} onRetry={() => image.refetch()} />;
  const detail = image.data;
  const size = { width: detail.width ?? 1920, height: detail.height ?? 1080 };
  const wanted = new Set(detectionIds);
  const boxes = detail.detections.filter((d) => wanted.has(d.id));
  const areaZones = (zones.data?.items ?? []).filter((z) => z.area === area);
  const camera = cameras.data?.items.find((c) => c.id === detail.camera_id);
  const name = (code: string) => classes.data?.get(code) ?? code;

  return (
    <div className="space-y-2">
      <Frame url={detail.url} alt={`Снимок ${formatMoment(detail.captured_at)}`} {...size}>
        {areaZones.map((zone) => (
          <ZoneOutline
            key={zone.id}
            polygon={zonePolygon(zone)}
            color={zoneColor(zone.zone_type)}
            label={zone.name}
            size={size}
            muted={boxes.length > 0}
          />
        ))}
        {boxes.map((d) => (
          <DetectionBox
            key={d.id}
            bbox={d.bbox}
            anchor={d.anchor}
            label={`${name(d.equipment_class)} ${d.conf.toFixed(2)}`}
            color={EVIDENCE_COLOR}
            size={size}
          />
        ))}
      </Frame>
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
        <span className="flex items-center gap-1.5">
          <Icon name="camera" size={14} />
          {camera?.name ?? "Камера"} · {formatMoment(detail.captured_at)}
        </span>
        <span>
          {boxes.length > 0 ? `рамок в выводе: ${boxes.length}` : "рамок нет: снимок показывает, что техники на участке не было"}
        </span>
        <Link
          to={`/objects/${objectId}/cameras?camera=${camera?.code ?? ""}&image=${imageId}`}
          className="ml-auto font-medium text-accent hover:underline"
        >
          открыть на экране камер →
        </Link>
      </p>
      {zones.isError && <ErrorBox error={zones.error} />}
    </div>
  );
}

function SessionsSection({
  deviation,
  explain,
  names,
}: {
  deviation: DeviationRead;
  explain: ExplainRead;
  names: (code: string) => string;
}) {
  if (explain.sessions == null) {
    return (
      <Section title="Проверенные сессии" icon="clock">
        <p className="text-sm text-muted">
          Факты сессий сейчас недоступны
          {explain.sessions_unavailable_reason ? `: ${explain.sessions_unavailable_reason}` : ""}.
        </p>
      </Section>
    );
  }
  const rows = sessionRows(explain.sessions, deviation.area ?? null, names);
  return (
    <Section title={`Проверенные сессии: ${rows.length}`} icon="clock">
      <div className="overflow-hidden rounded-xl ring-1 ring-ink/[0.08]">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="bg-stone-50 text-xs text-muted">
            <tr>
              <th className="px-3 py-2 font-medium">Окно</th>
              <th className="px-3 py-2 font-medium">Участок</th>
              <th className="px-3 py-2 font-medium">Техника на участке</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-ink/[0.06] align-top">
                <td className="whitespace-nowrap px-3 py-2 tabular-nums">{row.at}</td>
                <td className="px-3 py-2">{row.visibility}</td>
                <td className="px-3 py-2">{row.equipment}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {explain.sessions_truncated && <p className="mt-1.5 text-xs text-muted">Показаны не все сессии эпизода.</p>}
    </Section>
  );
}

function Section({
  title,
  icon,
  actions,
  children,
}: {
  title: string;
  icon: "gauge" | "rules" | "image" | "clock";
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        <Icon name={icon} size={16} className="text-muted" />
        <h3 className="font-semibold">{title}</h3>
        {actions && <div className="ml-auto">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

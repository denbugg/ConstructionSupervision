import { useEffect, useRef } from "react";
import { useParams } from "react-router-dom";

import { formatClock, formatDay } from "@/entities/format";
import { SEVERITY_ORDER, deviationStatusTone, severityDot } from "@/entities/status";
import { DeviationCard } from "@/features/deviations/DeviationCard";
import {
  DEFAULT_PRESET,
  STATUS_PRESETS,
  neighbour,
  useDeviationFilter,
  useDeviations,
  type StatusPreset,
} from "@/features/deviations/useDeviations";
import type { DeviationRead } from "@/shared/api/queries";
import { label, ru } from "@/shared/locale/ru";
import { Badge, Dot } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { fieldClass } from "@/shared/ui/Field";
import { PageHeader, Segmented } from "@/shared/ui/Page";
import { Empty, ErrorBox, Loading } from "@/shared/ui/QueryState";

const CODES = Object.keys(ru.deviationCode);

/**
 * Лента предупреждений (T30) — главный экран: правило, числа и снимок-доказательство
 * (apps/web/README.md, §3). Слева лента по дням, справа карточка выбранного отклонения.
 * ↑/↓ листают ленту; после вердикта открывается следующая карточка.
 */
export function DeviationsScreen() {
  const { objectId = "" } = useParams();
  const { filter, preset, selectedId, update } = useDeviationFilter();
  const { feed, items, selected } = useDeviations(objectId, filter, selectedId);
  const filtered = filter.codes.length > 0 || filter.severities.length > 0 || filter.from != null || filter.to != null;

  const go = (step: 1 | -1) => {
    const next = neighbour(items, selected, step);
    if (next) update({ id: next.id });
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.closest("input, textarea, select, [contenteditable]")) return;
      if (e.key === "ArrowDown" || e.key === "j") {
        e.preventDefault();
        go(1);
      }
      if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault();
        go(-1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div>
      <PageHeader
        title="Предупреждения"
        description="Что нарушено, по какому правилу, на каких числах и снимках. Подтвердите или отметьте ложным — вердикт остаётся в истории."
      />

      <div className="mb-5 flex flex-wrap items-center gap-3 rounded-2xl bg-white p-3 shadow-sm ring-1 ring-ink/[0.07]">
        <Segmented
          value={preset}
          onChange={(key: StatusPreset) => update({ status: key === DEFAULT_PRESET ? null : key, id: null })}
          options={(Object.keys(STATUS_PRESETS) as StatusPreset[]).map((key) => ({
            value: key,
            label: STATUS_PRESETS[key].label,
          }))}
        />
        <div className="flex flex-wrap items-center gap-1">
          {SEVERITY_ORDER.map((s) => {
            const active = filter.severities.includes(s);
            return (
              <button
                key={s}
                type="button"
                aria-pressed={active}
                onClick={() => update({ severity: active ? null : s, id: null })}
                className={`inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-sm transition-colors ${
                  active ? "bg-ink text-white" : "text-ink/70 hover:bg-ink/[0.06]"
                }`}
              >
                <Dot className={severityDot(s)} />
                {label(ru.severity, s)}
              </button>
            );
          })}
        </div>
        <select
          value={filter.codes[0] ?? ""}
          onChange={(e) => update({ code: e.target.value || null, id: null })}
          className={fieldClass("select", "sm", "w-auto max-w-60")}
          aria-label="Код отклонения"
        >
          <option value="">Все коды</option>
          {CODES.map((c) => (
            <option key={c} value={c}>
              {c} — {label(ru.deviationCode, c)}
            </option>
          ))}
        </select>
        <div className="flex items-center gap-1.5 text-sm text-muted">
          <input
            type="date"
            value={filter.from ?? ""}
            onChange={(e) => update({ from: e.target.value || null, id: null })}
            className={fieldClass("input", "sm", "w-auto")}
            aria-label="С даты"
          />
          —
          <input
            type="date"
            value={filter.to ?? ""}
            onChange={(e) => update({ to: e.target.value || null, id: null })}
            className={fieldClass("input", "sm", "w-auto")}
            aria-label="По дату"
          />
        </div>
        {filtered && (
          <Button size="sm" variant="ghost" icon="x" onClick={() => update({ code: null, severity: null, from: null, to: null, id: null })}>
            Сбросить
          </Button>
        )}
      </div>

      {feed.isPending && <Loading />}
      {feed.isError && <ErrorBox error={feed.error} onRetry={() => feed.refetch()} />}
      {feed.isSuccess && items.length === 0 && (
        <Empty
          icon={preset === "open" && !filtered ? "check" : "filter"}
          title={preset === "open" && !filtered ? "Открытых предупреждений нет" : "Под фильтр ничего не попало"}
          action={
            (filtered || preset !== "all") && (
              <Button onClick={() => update({ status: "all", code: null, severity: null, from: null, to: null, id: null })}>
                Показать всю ленту
              </Button>
            )
          }
        >
          {preset === "open" && !filtered
            ? "Лента заполняется прогоном анализа: он идёт сам после распознавания снимков и правки плана."
            : "Сбросьте часть условий или посмотрите всю ленту, включая закрытые."}
        </Empty>
      )}
      {items.length > 0 && (
        <div className="grid items-start gap-5 lg:grid-cols-[24rem_minmax(0,1fr)]">
          <Feed
            items={items}
            total={feed.data?.total ?? items.length}
            selected={selected}
            onSelect={(id) => update({ id })}
          />
          {selected && (
            <DeviationCard
              key={selected.id}
              objectId={objectId}
              deviation={selected}
              onVerdict={() => {
                const next = neighbour(items, selected, 1);
                if (next) update({ id: next.id });
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}

/** Лента по дням начала эпизода; внутри дня — как отдал API, новые сверху. */
function Feed({
  items,
  total,
  selected,
  onSelect,
}: {
  items: DeviationRead[];
  total: number;
  selected: DeviationRead | null;
  onSelect: (id: string) => void;
}) {
  const active = useRef<HTMLButtonElement>(null);
  // Тело блоком: в новых браузерах scrollIntoView возвращает Promise, а эффект — только очистку.
  useEffect(() => {
    active.current?.scrollIntoView({ block: "nearest" });
  }, [selected?.id]);

  const days = new Map<string, DeviationRead[]>();
  for (const item of items) {
    const day = formatDay(item.first_seen_at);
    days.set(day, [...(days.get(day) ?? []), item]);
  }
  return (
    <div className="rounded-2xl bg-white shadow-sm ring-1 ring-ink/[0.07] lg:sticky lg:top-20 lg:max-h-[calc(100vh-6.5rem)] lg:overflow-y-auto">
      <p className="sticky top-0 z-10 flex items-center justify-between border-b border-ink/[0.07] bg-white/95 px-4 py-2.5 text-xs text-muted backdrop-blur">
        <span>
          {total} {total > items.length && `· показаны последние ${items.length}`}
        </span>
        <span className="hidden lg:inline">↑ ↓ — листать</span>
      </p>
      {[...days].map(([day, group]) => (
        <div key={day}>
          <p className="px-4 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wider text-muted">{day}</p>
          <ul className="px-2 pb-1">
            {group.map((item) => {
              const current = item.id === selected?.id;
              return (
                <li key={item.id}>
                  <button
                    ref={current ? active : undefined}
                    type="button"
                    onClick={() => onSelect(item.id)}
                    className={`relative block w-full rounded-xl px-3 py-2.5 text-left text-sm transition-colors ${
                      current ? "bg-accent/[0.07] ring-1 ring-accent/40" : "hover:bg-canvas/70"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <Dot className={severityDot(item.severity)} />
                      <span className="font-mono text-xs font-semibold text-ink/70">{item.code}</span>
                      <Badge tone={deviationStatusTone(item.status)} size="sm">
                        {label(ru.deviationStatus, item.status)}
                      </Badge>
                      {item.verdict && item.status === "RESOLVED" && (
                        <Badge tone={deviationStatusTone(item.verdict)} size="sm">
                          {item.verdict === "REJECTED" ? "ложное" : "подтверждено"}
                        </Badge>
                      )}
                      <span className="ml-auto text-xs tabular-nums text-muted">
                        {formatClock(item.first_seen_at)}–{formatClock(item.last_seen_at)}
                      </span>
                    </span>
                    <span className={`mt-1 block leading-snug ${current ? "font-medium" : ""}`}>{item.title}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

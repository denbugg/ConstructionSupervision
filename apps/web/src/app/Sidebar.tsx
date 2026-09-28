import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation, useMatch, useNavigate } from "react-router-dom";

import { objectStatusDot, openDeviations } from "@/entities/status";
import { imageCountQuery, objectQuery, objectsQuery, statusQuery } from "@/shared/api/queries";
import { ru } from "@/shared/locale/ru";
import { Dot } from "@/shared/ui/Badge";
import { Icon, type IconName } from "@/shared/ui/Icon";

/**
 * Боковая навигация: все объекты, разделы открытого объекта и справочники системы. Разделы
 * объекта видны всегда, пока он открыт: из любого экрана в любой — один щелчок.
 */
export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const match = useMatch("/objects/:objectId/*");
  const onList = useMatch("/objects") != null;
  // Объект открыт, пока человек не вернулся к списку: из объекта в справочник и обратно —
  // один щелчок. Вернулся к списку — выбора больше нет, и справочник открывается без объекта,
  // иначе меню показывало бы объект, который человек сейчас не выбирал.
  const [lastId, setLastId] = useState<string | null>(null);
  const current = match?.params.objectId ?? null;
  useEffect(() => {
    if (current) setLastId(current);
    else if (onList) setLastId(null);
  }, [current, onList]);
  const objectId = current ?? lastId;

  return (
    <>
      {open && <div className="fixed inset-0 z-30 animate-fade-in bg-ink/40 lg:hidden" onClick={onClose} />}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-ink text-white/70 transition-transform duration-200 lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <Brand />
        <nav className="flex-1 space-y-6 overflow-y-auto px-3 pb-6">
          <div>
            <NavItem to="/objects" icon="building" end>
              Все объекты
            </NavItem>
          </div>
          {objectId && <ObjectNav objectId={objectId} />}
          <NavGroup title="Справочники системы">
            <NavItem to="/settings/deviation-rules" icon="gauge">
              Пороги отклонений
            </NavItem>
            <NavItem to="/settings/equipment" icon="truck">
              Классы техники
            </NavItem>
          </NavGroup>
        </nav>
        <footer className="border-t border-white/10 px-5 py-3 text-xs text-white/40">
          Время — московское (UTC+3)
        </footer>
      </aside>
    </>
  );
}

export function Brand() {
  return (
    <div className="flex items-center gap-3 px-5 py-5">
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-white shadow-sm">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M6 21V4M6 4h14M6 4l-3 3M17 4v5M15 9h4v3h-4zM3 21h8" />
        </svg>
      </span>
      <div className="leading-tight">
        <p className="font-semibold text-white">{ru.app.title}</p>
        <p className="text-xs text-white/50">контроль стройки по камерам</p>
      </div>
    </div>
  );
}

function ObjectNav({ objectId }: { objectId: string }) {
  const status = useQuery(statusQuery(objectId));
  const needsTime = useQuery(imageCountQuery(objectId, "NEEDS_TIME"));
  const base = `/objects/${objectId}`;
  const open = status.data ? openDeviations(status.data.deviations) : null;
  const high = status.data?.deviations.HIGH ?? 0;

  return (
    <>
      <NavGroup title="Объект">
        <ObjectSwitcher objectId={objectId} />
        <NavItem to={base} end icon="home">
          Обзор
        </NavItem>
        <NavItem to={`${base}/deviations`} icon="alert" badge={open || null} badgeTone={high > 0 ? "alert" : "plain"}>
          Предупреждения
        </NavItem>
        <NavItem to={`${base}/gantt`} icon="gantt">
          График план-факт
        </NavItem>
        <NavItem to={`${base}/cameras`} icon="camera">
          Камеры
        </NavItem>
        <NavItem to={`${base}/upload`} icon="upload" badge={needsTime.data || null} badgeTone="warn">
          Загрузка снимков
        </NavItem>
        <NavItem to={`${base}/reports`} icon="report">
          Отчёты
        </NavItem>
      </NavGroup>
      <NavGroup title="Настройка объекта">
        <NavItem to={`${base}/settings`} end icon="sliders">
          Реквизиты и график
        </NavItem>
        <NavItem to={`${base}/settings/rules`} icon="rules">
          Правила «этап → техника»
        </NavItem>
        <NavItem to={`${base}/settings/zones`} icon="zones">
          Зоны на камерах
        </NavItem>
      </NavGroup>
    </>
  );
}

/**
 * Переключатель объекта. Раздел сохраняется: из ленты предупреждений одного объекта — в
 * ленту другого, без возврата к списку.
 */
function ObjectSwitcher({ objectId }: { objectId: string }) {
  const current = useQuery(objectQuery(objectId));
  const objects = useQuery(objectsQuery);
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { pathname } = useLocation();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const section = pathname.slice(`/objects/${objectId}`.length);
  const items = (objects.data?.items ?? []).filter((o) => o.status !== "ARCHIVED" || o.id === objectId);

  return (
    <div ref={root} className="relative mb-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-lg bg-white/[0.06] px-3 py-2.5 text-left text-sm text-white ring-1 ring-white/10 hover:bg-white/10"
      >
        <span className="line-clamp-2 min-w-0 flex-1 font-medium leading-snug">{current.data?.name ?? "…"}</span>
        <Icon name="chevronDown" size={15} className="text-white/50" />
      </button>
      {open && (
        <div className="absolute inset-x-0 top-full z-50 mt-1 max-h-80 animate-pop-in overflow-y-auto rounded-xl bg-white py-1.5 text-ink shadow-xl ring-1 ring-ink/10">
          {items.map((o) => (
            <SwitcherItem
              key={o.id}
              id={o.id}
              name={o.name}
              active={o.id === objectId}
              onPick={() => {
                setOpen(false);
                navigate(`/objects/${o.id}${section}`);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function SwitcherItem({ id, name, active, onPick }: { id: string; name: string; active: boolean; onPick: () => void }) {
  const status = useQuery(statusQuery(id));
  return (
    <button
      type="button"
      onClick={onPick}
      className={`flex w-full items-start gap-2 px-3 py-2 text-left text-sm hover:bg-ink/[0.05] ${active ? "font-medium" : ""}`}
    >
      <Dot className={`mt-1.5 ${objectStatusDot(status.data?.status)}`} />
      <span className="line-clamp-2">{name}</span>
      {active && <Icon name="check" size={15} className="ml-auto mt-0.5 text-accent" />}
    </button>
  );
}

function NavGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wider text-white/35">{title}</p>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

const BADGE = {
  alert: "bg-red-500 text-white",
  warn: "bg-amber-400 text-ink",
  plain: "bg-white/15 text-white",
};

function NavItem({
  to,
  icon,
  end = false,
  badge = null,
  badgeTone = "plain",
  children,
}: {
  to: string;
  icon: IconName;
  end?: boolean;
  badge?: number | null;
  badgeTone?: keyof typeof BADGE;
  children: ReactNode;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
          isActive ? "bg-white/10 font-medium text-white" : "hover:bg-white/[0.06] hover:text-white"
        }`
      }
    >
      {({ isActive }) => (
        <>
          {isActive && <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-accent" />}
          <Icon name={icon} size={17} className={isActive ? "text-accent" : "text-white/45 group-hover:text-white/70"} />
          <span className="min-w-0 flex-1 truncate">{children}</span>
          {badge != null && (
            <span className={`rounded-full px-1.5 py-px text-[11px] font-semibold tabular-nums ${BADGE[badgeTone]}`}>{badge}</span>
          )}
        </>
      )}
    </NavLink>
  );
}

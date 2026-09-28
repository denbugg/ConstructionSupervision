/**
 * Черновик разметки одной камеры. Правки копятся локально и уходят в site-service одной
 * кнопкой: каждое сохранение зоны ставит пересчёт фактов всех окон объекта (`reapply_zones`),
 * и сохранять на каждое движение вершины — значит гонять пересчёт десятки раз подряд.
 */
import {
  insertVertex,
  moveVertex,
  removeVertex,
  samePolygon,
  translate,
  type Point,
} from "@/entities/polygon";
import type { ZoneRead } from "@/shared/api/queries";
import type { ZoneType } from "@/shared/locale/ru";

export type DraftZone = {
  /** id зоны в site-service или `new-N` для ещё не сохранённой. */
  key: string;
  id: string | null;
  zoneType: ZoneType;
  name: string;
  polygon: Point[];
  deleted: boolean;
  /** Как зона выглядит на сервере; у новой — null. */
  saved: { zoneType: ZoneType; name: string; polygon: Point[] } | null;
};

export type Draft = { zones: DraftZone[]; selected: string | null; nextNew: number };

export type Action =
  | { type: "reset"; zones: ZoneRead[] }
  | { type: "select"; key: string | null }
  | { type: "add"; polygon: Point[]; zoneType: ZoneType }
  | { type: "moveVertex"; key: string; index: number; to: Point }
  | { type: "insertVertex"; key: string; after: number; at: Point }
  | { type: "removeVertex"; key: string; index: number }
  | { type: "translate"; key: string; from: Point[]; dx: number; dy: number }
  | { type: "setType"; key: string; zoneType: ZoneType }
  | { type: "setName"; key: string; name: string }
  | { type: "delete"; key: string }
  | { type: "restore"; key: string }
  /** Зона сохранена на сервере: `zone` — ответ сервера, null — зона удалена. */
  | { type: "committed"; key: string; zone: ZoneRead | null };

export function fromServer(zones: ZoneRead[]): Draft {
  return {
    selected: null,
    nextNew: 1,
    zones: zones.map((z) => {
      const polygon = z.polygon.map(([x, y]) => [x, y] as Point);
      const zoneType = z.zone_type as ZoneType;
      return {
        key: z.id,
        id: z.id,
        zoneType,
        name: z.name,
        polygon,
        deleted: false,
        saved: { zoneType, name: z.name, polygon },
      };
    }),
  };
}

function update(draft: Draft, key: string, change: (z: DraftZone) => DraftZone): Draft {
  return { ...draft, zones: draft.zones.map((z) => (z.key === key ? change(z) : z)) };
}

export function reducer(draft: Draft, action: Action): Draft {
  switch (action.type) {
    case "reset":
      return fromServer(action.zones);
    case "select":
      return { ...draft, selected: action.key };
    case "add": {
      const key = `new-${draft.nextNew}`;
      const zone: DraftZone = {
        key,
        id: null,
        zoneType: action.zoneType,
        name: "",
        polygon: action.polygon,
        deleted: false,
        saved: null,
      };
      return { zones: [...draft.zones, zone], selected: key, nextNew: draft.nextNew + 1 };
    }
    case "moveVertex":
      return update(draft, action.key, (z) => ({
        ...z,
        polygon: moveVertex(z.polygon, action.index, action.to),
      }));
    case "insertVertex":
      return update(draft, action.key, (z) => ({
        ...z,
        polygon: insertVertex(z.polygon, action.after, action.at),
      }));
    case "removeVertex":
      return update(draft, action.key, (z) => ({
        ...z,
        polygon: removeVertex(z.polygon, action.index),
      }));
    case "translate":
      // Сдвиг — от полигона на момент нажатия, а не накопленными шагами: иначе упор в край
      // кадра на одном шаге терял бы часть движения навсегда.
      return update(draft, action.key, (z) => ({
        ...z,
        polygon: translate(action.from, action.dx, action.dy),
      }));
    case "setType":
      return update(draft, action.key, (z) => ({ ...z, zoneType: action.zoneType }));
    case "setName":
      return update(draft, action.key, (z) => ({ ...z, name: action.name }));
    case "delete": {
      const zone = draft.zones.find((z) => z.key === action.key);
      // Несохранённая зона просто исчезает; сохранённая помечается и удалится при сохранении.
      const zones =
        zone?.id == null
          ? draft.zones.filter((z) => z.key !== action.key)
          : draft.zones.map((z) => (z.key === action.key ? { ...z, deleted: true } : z));
      return { ...draft, zones, selected: null };
    }
    case "restore":
      return update(draft, action.key, (z) => ({ ...z, deleted: false }));
    case "committed": {
      const { zone } = action;
      if (zone == null) {
        return { ...draft, zones: draft.zones.filter((z) => z.key !== action.key) };
      }
      // Ключ остаётся прежним, чтобы не сбросить выбор; id и «как на сервере» — из ответа.
      return update(draft, action.key, (z) => ({
        ...z,
        id: zone.id,
        name: zone.name,
        saved: {
          zoneType: zone.zone_type as ZoneType,
          name: zone.name,
          polygon: zone.polygon.map(([x, y]) => [x, y] as Point),
        },
      }));
    }
  }
}

export type Change =
  | { kind: "create"; zone: DraftZone }
  | { kind: "update"; zone: DraftZone; fields: Record<string, unknown> }
  | { kind: "delete"; zone: DraftZone };

/** Что уйдёт на сервер: только отличия от сохранённого. Имя сравнивается без краевых пробелов. */
export function changes(draft: Draft): Change[] {
  const out: Change[] = [];
  for (const zone of draft.zones) {
    if (zone.saved == null) {
      if (!zone.deleted) out.push({ kind: "create", zone });
      continue;
    }
    if (zone.deleted) {
      out.push({ kind: "delete", zone });
      continue;
    }
    const fields: Record<string, unknown> = {};
    if (zone.zoneType !== zone.saved.zoneType) fields.zone_type = zone.zoneType;
    const name = zone.name.trim();
    if (name && name !== zone.saved.name) fields.name = name;
    if (!samePolygon(zone.polygon, zone.saved.polygon)) fields.polygon = zone.polygon;
    if (Object.keys(fields).length > 0) out.push({ kind: "update", zone, fields });
  }
  return out;
}

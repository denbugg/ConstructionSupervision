/**
 * Зоны и участки на экране: порядок типов, цвета, подпись участка. Названия типов — в
 * `shared/locale/ru.ts`, роли — в enums.yaml; здесь только то, что нужно для рисования.
 */
import { ru, type ZoneType } from "@/shared/locale/ru";

/** Типы зон в порядке enums.yaml: так же их видит оператор в списке выбора. */
export const ZONE_TYPES = Object.keys(ru.zoneType) as ZoneType[];

// Цвет — по роли типа: рабочие участки холодные, служебные тёплые, опасная зона красная.
// Внутри роли оттенки разные, чтобы соседние зоны не сливались.
const ZONE_COLORS: Record<ZoneType, string> = {
  PIT: "#2563eb",
  BUILDING_FOOTPRINT: "#0d9488",
  PERIMETER: "#7c3aed",
  ROAD: "#475569",
  ENTRY_GATE: "#d97706",
  STORAGE: "#a16207",
  DANGER: "#dc2626",
};

export function zoneColor(zoneType: string): string {
  return ZONE_COLORS[zoneType as ZoneType] ?? "#64748b";
}

export function isZoneType(value: string): value is ZoneType {
  return value in ru.zoneType;
}

/**
 * Подпись участка `ТИП:Название`, как её строит site-service (ADR-0013): пустое название —
 * название типа. Одинаковая подпись на разных камерах — один участок.
 */
export function areaKey(zoneType: ZoneType, name: string): string {
  return `${zoneType}:${name.trim() || ru.zoneType[zoneType]}`;
}

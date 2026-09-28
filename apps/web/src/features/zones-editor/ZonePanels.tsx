import { useQuery } from "@tanstack/react-query";

import { selfIntersects, type Point } from "@/entities/polygon";
import { ZONE_TYPES, areaKey, isZoneType, zoneColor } from "@/entities/zones";
import type { Action, DraftZone } from "@/features/zones-editor/draft";
import { saveErrorText, type useZonesEditor } from "@/features/zones-editor/useZonesEditor";
import { areasQuery, type CameraRead } from "@/shared/api/queries";
import { ru, type ZoneType } from "@/shared/locale/ru";
import { Button } from "@/shared/ui/Button";
import { Field, fieldClass, inputClass, selectClass } from "@/shared/ui/Field";
import { Icon } from "@/shared/ui/Icon";
import { Panel } from "@/shared/ui/Page";
import { useToast } from "@/shared/ui/Toast";

/** Панель инструментов кадра: новая зона выбранного типа или подсказка режима рисования. */
export function Toolbar({
  drawing,
  newType,
  onNewType,
  onStart,
  onFinish,
  onCancel,
}: {
  drawing: Point[] | null;
  newType: ZoneType;
  onNewType: (t: ZoneType) => void;
  onStart: () => void;
  onFinish: () => void;
  onCancel: () => void;
}) {
  if (!drawing) {
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-2xl bg-white p-2.5 shadow-sm ring-1 ring-ink/[0.07]">
        <span className="h-3 w-3 shrink-0 rounded-sm" style={{ background: zoneColor(newType) }} />
        <select
          value={newType}
          onChange={(e) => isZoneType(e.target.value) && onNewType(e.target.value)}
          className={fieldClass("select", "sm", "w-auto")}
          aria-label="Тип новой зоны"
        >
          {ZONE_TYPES.map((t) => (
            <option key={t} value={t}>
              {ru.zoneType[t]}
            </option>
          ))}
        </select>
        <Button size="sm" variant="dark" icon="plus" onClick={onStart}>
          Нарисовать зону
        </Button>
        <span className="ml-auto hidden text-xs text-muted md:inline">{ru.zoneRole[newType]}</span>
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-2xl bg-accent/[0.07] p-2.5 text-sm ring-1 ring-accent/30">
      <Icon name="zones" size={16} className="text-accent" />
      <span className="flex-1">
        Новая зона «{ru.zoneType[newType]}»: щёлкайте по углам участка. Замкнуть — щелчок по первой
        точке или Enter; Backspace убирает последнюю точку, Esc — отмена.
      </span>
      <Button size="sm" variant="primary" icon="check" onClick={onFinish} disabled={drawing.length < 3}>
        Готово
      </Button>
      <Button size="sm" variant="ghost" onClick={onCancel}>
        Отмена
      </Button>
    </div>
  );
}

/** Несохранённые правки и кнопка «Сохранить»: одна на все зоны камеры. */
export function SavePanel({ editor }: { editor: ReturnType<typeof useZonesEditor> }) {
  const toast = useToast();
  const count = editor.pending.length;
  const invalid = editor.draft.zones.some((z) => !z.deleted && selfIntersects(z.polygon));
  return (
    <div
      className={`space-y-2.5 rounded-2xl p-4 shadow-sm ring-1 ${
        count > 0 ? "bg-accent/[0.05] ring-accent/30" : "bg-white ring-ink/[0.07]"
      }`}
    >
      <p className="flex items-center gap-2 text-sm font-medium">
        <Icon name={count === 0 ? "check" : "edit"} size={16} className={count === 0 ? "text-emerald-600" : "text-accent"} />
        {count === 0 ? "Все правки сохранены" : `Несохранённых изменений: ${count}`}
      </p>
      {invalid && <p className="text-sm text-red-700">Есть зона с пересекающимися сторонами — такую сервис не примет.</p>}
      <div className="flex gap-2">
        <Button
          variant="primary"
          icon="check"
          onClick={() =>
            editor.save.mutate(undefined, {
              onSuccess: (outcomes) => {
                const failed = outcomes.filter((o) => "error" in o).length;
                if (failed === 0) toast.success("Зоны сохранены", "Факты окон и выводы пересчитаются в фоне");
                else toast.info(`Не сохранено зон: ${failed}`, "Причина — у зоны в списке");
              },
              onError: (error) => toast.error(error, "Зоны не сохранены"),
            })
          }
          disabled={count === 0 || invalid}
          loading={editor.save.isPending}
          className="flex-1"
        >
          Сохранить
        </Button>
        <Button variant="ghost" onClick={editor.discard} disabled={count === 0 || editor.save.isPending}>
          Отменить
        </Button>
      </div>
      {editor.errors.size > 0 && <p className="text-sm text-red-700">Не сохранено зон: {editor.errors.size}. Причина — у зоны в списке.</p>}
    </div>
  );
}

/** Свойства выбранной зоны: тип, название-участок и связь с участками других камер. */
export function ZoneProperties({
  zone,
  objectId,
  camera,
  error,
  dispatch,
}: {
  zone: DraftZone;
  objectId: string;
  camera: CameraRead;
  error: unknown;
  dispatch: (action: Action) => void;
}) {
  const areas = useQuery(areasQuery(objectId));
  const key = areaKey(zone.zoneType, zone.name);
  const sameType = (areas.data?.areas ?? []).filter((a) => a.zone_type === zone.zoneType);
  const shared = sameType
    .find((a) => a.area === key)
    ?.cameras.filter((c) => c.camera_id !== camera.id)
    .map((c) => c.camera_code);

  return (
    <Panel title="Выбранная зона" icon="zones" bodyClassName="p-4 space-y-4 text-sm">
      <Field label="Тип участка" hint={`Роль: ${ru.zoneRole[zone.zoneType]}`}>
        <select
          value={zone.zoneType}
          onChange={(e) => isZoneType(e.target.value) && dispatch({ type: "setType", key: zone.key, zoneType: e.target.value })}
          className={selectClass}
        >
          {ZONE_TYPES.map((t) => (
            <option key={t} value={t}>
              {ru.zoneType[t]}
            </option>
          ))}
        </select>
      </Field>
      <Field
        label="Название участка"
        hint={`Участок: ${key}${
          shared && shared.length > 0 ? ` — тот же участок, что на ${shared.join(", ")}` : " — на других камерах такого участка нет"
        }`}
      >
        <input
          value={zone.name}
          onChange={(e) => dispatch({ type: "setName", key: zone.key, name: e.target.value })}
          placeholder={ru.zoneType[zone.zoneType]}
          list="area-names"
          className={inputClass}
        />
      </Field>
      <datalist id="area-names">
        {sameType.map((a) => (
          <option key={a.area} value={a.name} />
        ))}
      </datalist>
      <p className="text-xs text-muted">Вершин: {zone.polygon.length}</p>
      {error != null && <p className="text-red-700">Не сохранено: {saveErrorText(error)}</p>}
      <Button size="sm" variant="ghost" icon="trash" className="-ml-2.5 !text-red-700 hover:!bg-red-50" onClick={() => dispatch({ type: "delete", key: zone.key })}>
        Удалить зону
      </Button>
    </Panel>
  );
}

export function ZoneList({
  zones,
  selected,
  errors,
  dispatch,
}: {
  zones: DraftZone[];
  selected: string | null;
  errors: Map<string, unknown>;
  dispatch: (action: Action) => void;
}) {
  return (
    <Panel title={`Зоны камеры: ${zones.filter((z) => !z.deleted).length}`} icon="layers" bodyClassName="p-2">
      {zones.length === 0 && <p className="px-2 py-3 text-sm text-muted">Зон нет. Выберите тип и нажмите «Нарисовать зону».</p>}
      <ul>
        {zones.map((zone) => (
          <li key={zone.key}>
            {zone.deleted ? (
              <div className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm">
                <span className="h-3 w-3 shrink-0 rounded-sm opacity-40" style={{ background: zoneColor(zone.zoneType) }} />
                <span className="flex-1 text-muted line-through">{zone.name || ru.zoneType[zone.zoneType]}</span>
                <button type="button" onClick={() => dispatch({ type: "restore", key: zone.key })} className="text-xs font-medium text-accent hover:underline">
                  вернуть
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => dispatch({ type: "select", key: zone.key })}
                className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm ${
                  zone.key === selected ? "bg-accent/[0.07] font-medium ring-1 ring-accent/30" : "hover:bg-canvas/70"
                }`}
              >
                <span className="h-3 w-3 shrink-0 rounded-sm" style={{ background: zoneColor(zone.zoneType) }} />
                <span className="min-w-0 flex-1 truncate">
                  {zone.name || ru.zoneType[zone.zoneType]}
                  <span className="font-normal text-muted"> · {ru.zoneType[zone.zoneType]}</span>
                </span>
                {zone.saved == null && <span className="text-xs text-accent">новая</span>}
                {errors.has(zone.key) && <span className="text-xs text-red-700">не сохранена</span>}
              </button>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

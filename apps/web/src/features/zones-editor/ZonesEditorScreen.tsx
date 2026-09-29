import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import type { Point } from "@/entities/polygon";
import { countByClass, useCameraAnchors, useImage, useSelectedCamera } from "@/features/cameras/useCameras";
import { EditorCanvas } from "@/features/zones-editor/EditorCanvas";
import { SavePanel, Toolbar, ZoneList, ZoneProperties } from "@/features/zones-editor/ZonePanels";
import { useZonesEditor } from "@/features/zones-editor/useZonesEditor";
import { equipmentClassesQuery, type CameraRead } from "@/shared/api/queries";
import type { ZoneType } from "@/shared/locale/ru";
import { ButtonLink } from "@/shared/ui/Button";
import { CameraTabs } from "@/shared/ui/CameraTabs";
import { Icon } from "@/shared/ui/Icon";
import { useConfirm } from "@/shared/ui/Modal";
import { PageHeader } from "@/shared/ui/Page";
import { Empty, ErrorBox, Loading } from "@/shared/ui/QueryState";

/**
 * Редактор зон (F11): полигоны участков на эталонном кадре камеры. Одинаковые тип и
 * название на разных камерах — один участок (ADR-0013): так участок, видимый двумя камерами,
 * остаётся видимым, когда одну из них закрыли.
 */
export function ZonesEditorScreen() {
  const { objectId = "" } = useParams();
  const { cameras, items, camera, select } = useSelectedCamera(objectId);
  const [dirty, setDirty] = useState(false);
  const confirm = useConfirm();

  const switchCamera = async (next: CameraRead) => {
    if (next.id === camera?.id) return;
    if (dirty) {
      const ok = await confirm({
        title: "Уйти без сохранения?",
        message: "На этой камере есть несохранённые правки зон. При переходе к другой камере они пропадут.",
        confirmLabel: "Перейти без сохранения",
        tone: "danger",
      });
      if (!ok) return;
    }
    select(next);
  };

  return (
    <div>
      <PageHeader
        title="Зоны на камерах"
        description="Участок — это тип и название. Одинаковые тип и название на разных камерах — один участок: техника на нём считается по всем камерам, а видимым он остаётся, пока его видит хоть одна."
        actions={
          camera && (
            <ButtonLink to={`/objects/${objectId}/cameras?camera=${camera.code}`} size="sm" icon="camera">
              Снимки камеры
            </ButtonLink>
          )
        }
      />
      {cameras.isPending && <Loading />}
      {cameras.isError && <ErrorBox error={cameras.error} onRetry={() => cameras.refetch()} />}
      {cameras.isSuccess && items.length === 0 && (
        <Empty
          icon="zones"
          title="Размечать пока не на чем"
          action={
            <ButtonLink to={`/objects/${objectId}/upload`} variant="primary" icon="upload">
              Загрузить снимки
            </ButtonLink>
          }
        >
          У объекта нет камер: они появляются при загрузке снимков, а первый снимок становится
          эталонным кадром для разметки.
        </Empty>
      )}
      {camera && (
        <div className="space-y-4">
          <CameraTabs cameras={items} current={camera} onSelect={switchCamera} />
          <CameraEditor key={camera.id} camera={camera} objectId={objectId} onDirty={setDirty} />
        </div>
      )}
    </div>
  );
}

function CameraEditor({
  camera,
  objectId,
  onDirty,
}: {
  camera: CameraRead;
  objectId: string;
  onDirty: (dirty: boolean) => void;
}) {
  const reference = useImage(camera.reference_image_id);
  const editor = useZonesEditor(camera);
  const [drawing, setDrawing] = useState<Point[] | null>(null);
  const [newType, setNewType] = useState<ZoneType>("PIT");
  const [showAnchors, setShowAnchors] = useState(false);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const anchors = useCameraAnchors(camera.id, showAnchors);
  const classes = useQuery(equipmentClassesQuery);
  const dirty = editor.pending.length > 0;

  useEffect(() => onDirty(dirty), [dirty, onDirty]);
  useEffect(() => {
    // Закрытие вкладки с несохранёнными правками: браузер спросит сам.
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  useEffect(() => {
    if (!drawing) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawing(null);
      if (e.key === "Backspace") setDrawing((p) => (p ? p.slice(0, -1) : p));
      if (e.key === "Enter" && drawing.length >= 3) finishDrawing(drawing);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const finishDrawing = (points: Point[]) => {
    editor.dispatch({ type: "add", polygon: points, zoneType: newType });
    setDrawing(null);
  };

  if (camera.reference_image_id == null) {
    return (
      <Empty
        icon="image"
        title="У камеры нет эталонного кадра"
        action={
          <ButtonLink to={`/objects/${objectId}/cameras?camera=${camera.code}`} icon="camera">
            Выбрать кадр на экране камер
          </ButtonLink>
        }
      >
        Эталонный кадр появляется с первым загруженным снимком — на нём и размечают зоны.
      </Empty>
    );
  }
  if (reference.isPending || editor.zones.isPending) return <Loading />;
  if (reference.isError) return <ErrorBox error={reference.error} onRetry={() => reference.refetch()} />;
  if (editor.zones.isError) {
    return <ErrorBox error={editor.zones.error} onRetry={() => editor.zones.refetch()} />;
  }
  const size = { width: reference.data.width ?? 1920, height: reference.data.height ?? 1080 };
  const selected = editor.draft.zones.find((z) => z.key === editor.draft.selected && !z.deleted);
  const counts = countByClass(anchors.anchors.map((a) => ({ equipment_class: a.equipmentClass })));
  const color = anchorColors([...counts.keys()]);
  const points = anchors.anchors
    .filter((a) => !hidden.has(a.equipmentClass))
    .map((a) => ({ id: a.id, point: a.point, color: color.get(a.equipmentClass) ?? "#c2451a" }));
  const toggle = (code: string) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="space-y-3">
        <Toolbar
          drawing={drawing}
          newType={newType}
          onNewType={setNewType}
          onStart={() => {
            editor.dispatch({ type: "select", key: null });
            setDrawing([]);
          }}
          onFinish={() => drawing && drawing.length >= 3 && finishDrawing(drawing)}
          onCancel={() => setDrawing(null)}
        />
        <EditorCanvas
          url={reference.data.url}
          size={size}
          zones={editor.draft.zones}
          selected={editor.draft.selected}
          drawing={drawing}
          anchors={showAnchors ? points : []}
          onDraw={(next, finished) => (finished && next ? finishDrawing(next) : setDrawing(next))}
          dispatch={editor.dispatch}
        />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={showAnchors} onChange={(e) => setShowAnchors(e.target.checked)} />
            где стояла техника на всех снимках камеры
          </label>
          {showAnchors && anchors.isPending && <span className="text-muted">загружаем снимки…</span>}
          {showAnchors &&
            [...counts].map(([code, count]) => (
              <label key={code} className="flex items-center gap-1.5">
                <input type="checkbox" checked={!hidden.has(code)} onChange={() => toggle(code)} />
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color.get(code) }} />
                {classes.data?.get(code) ?? code}: {count}
              </label>
            ))}
        </div>
        {showAnchors && anchors.error != null && <ErrorBox error={anchors.error} />}
        <p className="flex gap-2 text-xs text-muted">
          <Icon name="info" size={14} className="mt-px shrink-0" />
          Вершину тяните мышью, «+» на ребре добавляет вершину, двойной щелчок по вершине удаляет
          её. Зону целиком двигают за её внутреннюю часть. Машина относится к зоне по нижней
          середине своей рамки — к точке, где она стоит на земле; размечайте с запасом.
        </p>
      </div>
      <aside className="space-y-4 lg:sticky lg:top-20">
        <SavePanel editor={editor} />
        {selected ? (
          <ZoneProperties
            zone={selected}
            objectId={objectId}
            camera={camera}
            error={editor.errors.get(selected.key)}
            dispatch={editor.dispatch}
          />
        ) : (
          <p className="rounded-2xl border border-dashed border-ink/15 px-4 py-3 text-sm text-muted">
            Выберите зону на кадре или в списке, чтобы изменить её.
          </p>
        )}
        <ZoneList zones={editor.draft.zones} selected={editor.draft.selected} errors={editor.errors} dispatch={editor.dispatch} />
      </aside>
    </div>
  );
}

// Цвета точек по классам: контрастные между собой и с цветами зон, по порядку появления.
const ANCHOR_PALETTE = ["#e11d48", "#f59e0b", "#10b981", "#06b6d4", "#8b5cf6", "#ec4899", "#84cc16", "#f97316"];

function anchorColors(codes: string[]): Map<string, string> {
  return new Map(codes.map((code, i) => [code, ANCHOR_PALETTE[i % ANCHOR_PALETTE.length] ?? "#c2451a"]));
}

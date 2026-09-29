import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { formatMoment } from "@/entities/format";
import { isZoneType, zoneColor } from "@/entities/zones";
import { CreateCameraDialog, RenameCameraDialog } from "@/features/cameras/CameraDialogs";
import {
  countByClass,
  dayOf,
  groupByDay,
  movement,
  timeOf,
  useCameraImages,
  useImage,
  useSelectedCamera,
  useSelectedImage,
  useSetReference,
  useUpdateCamera,
  useZones,
  zonePolygon,
} from "@/features/cameras/useCameras";
import { useReanalyze } from "@/features/upload/useUpload";
import {
  equipmentClassesQuery,
  type CameraRead,
  type ImageDetail,
  type ImageRead,
  type ZoneRead,
} from "@/shared/api/queries";
import { label, ru } from "@/shared/locale/ru";
import { Badge } from "@/shared/ui/Badge";
import { Button, ButtonLink, IconButton } from "@/shared/ui/Button";
import { CameraTabs } from "@/shared/ui/CameraTabs";
import { Frame } from "@/shared/ui/Frame";
import { Icon } from "@/shared/ui/Icon";
import { Menu } from "@/shared/ui/Menu";
import { useConfirm } from "@/shared/ui/Modal";
import { DetectionBox, ZoneOutline } from "@/shared/ui/overlays";
import { PageHeader, Panel } from "@/shared/ui/Page";
import { Empty, ErrorBox, Loading } from "@/shared/ui/QueryState";
import { useToast } from "@/shared/ui/Toast";

const DETECTION_COLOR = "#c2451a";

/**
 * Просмотр камеры: снимок, зоны камеры и рамки детекций, переключение камер и снимков
 * по времени. Здесь видно, что увидело распознавание и в какую зону site отнёс каждую машину.
 */
export function CamerasScreen() {
  const { objectId = "" } = useParams();
  const { cameras, items, camera, select } = useSelectedCamera(objectId);
  const [creating, setCreating] = useState(false);

  return (
    <div>
      <PageHeader
        title="Камеры"
        description="Что увидело распознавание: рамки техники, зоны участков и куда отнесена каждая машина. ← → листают снимки."
        actions={
          <>
            <Button icon="plus" onClick={() => setCreating(true)}>
              Камера
            </Button>
            <ButtonLink to={`/objects/${objectId}/upload`} icon="upload">
              Загрузить снимки
            </ButtonLink>
          </>
        }
      />

      {cameras.isPending && <Loading />}
      {cameras.isError && <ErrorBox error={cameras.error} onRetry={() => cameras.refetch()} />}
      {cameras.isSuccess && items.length === 0 && (
        <Empty
          icon="camera"
          title="Камер пока нет"
          action={
            <ButtonLink to={`/objects/${objectId}/upload`} variant="primary" icon="upload">
              Загрузить снимки
            </ButtonLink>
          }
        >
          Камера появляется сама при загрузке снимков из папки с её кодом
          (<code className="rounded bg-ink/5 px-1">cam-north/…</code>). Завести заранее — кнопкой «Камера».
        </Empty>
      )}
      {camera && (
        <div className="space-y-4">
          <CameraTabs cameras={items} current={camera} onSelect={select} />
          <CameraBar camera={camera} objectId={objectId} />
          <CameraView key={camera.id} camera={camera} />
        </div>
      )}
      {creating && <CreateCameraDialog objectId={objectId} onClose={() => setCreating(false)} onCreated={select} />}
    </div>
  );
}

/** Сведения и действия выбранной камеры: переименовать, выключить, распознать заново, зоны. */
function CameraBar({ camera, objectId }: { camera: CameraRead; objectId: string }) {
  const update = useUpdateCamera(camera);
  const reanalyze = useReanalyze(objectId);
  const zones = useZones(camera.id);
  const confirm = useConfirm();
  const toast = useToast();
  const [renaming, setRenaming] = useState(false);

  const toggle = async () => {
    if (camera.is_active) {
      const ok = await confirm({
        title: `Выключить камеру «${camera.name}»?`,
        message:
          "Её зоны тоже выключатся, факты окон пересчитаются: участки, которые видела только она, станут слепыми. Снимки и история сохранятся, включить можно обратно.",
        confirmLabel: "Выключить",
        tone: "danger",
      });
      if (!ok) return;
    }
    update.mutate(
      { is_active: !camera.is_active },
      {
        onSuccess: () => toast.success(camera.is_active ? "Камера выключена" : "Камера включена", "Факты окон пересчитываются в фоне"),
        onError: (error) => toast.error(error),
      },
    );
  };

  const rerun = async () => {
    const ok = await confirm({
      title: `Распознать снимки «${camera.name}» заново?`,
      message: "Нужно после смены модели или её порога. Снимки камеры снова встанут в очередь распознавания.",
      confirmLabel: "Распознать заново",
    });
    if (ok)
      reanalyze.mutate(camera.id, {
        onSuccess: (r) => toast.success(`В очереди снова: ${r.images} снимков`),
        onError: (error) => toast.error(error),
      });
  };

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-sm ring-1 ring-ink/[0.07]">
      <div className="min-w-0 flex-1">
        <p className="font-medium">
          {camera.name} <code className="ml-1 text-xs font-normal text-muted">{camera.code}</code>
        </p>
        <p className="text-xs text-muted">
          {camera.is_active ? "включена" : "выключена — в анализе не участвует"} · зон: {zones.data?.total ?? "…"} ·{" "}
          {camera.reference_image_id ? "эталонный кадр есть" : "эталонного кадра нет"}
        </p>
      </div>
      <ButtonLink to={`/objects/${objectId}/settings/zones?camera=${camera.code}`} size="sm" icon="zones">
        Разметить зоны
      </ButtonLink>
      <Menu
        size="sm"
        variant="secondary"
        label="Действия с камерой"
        items={[
          { label: "Переименовать", icon: "edit", onSelect: () => setRenaming(true) },
          { label: "Распознать снимки заново", icon: "refresh", onSelect: rerun },
          "divider",
          camera.is_active
            ? { label: "Выключить камеру", icon: "power", tone: "danger", onSelect: toggle }
            : { label: "Включить камеру", icon: "power", onSelect: toggle },
        ]}
      />
      {renaming && <RenameCameraDialog camera={camera} onClose={() => setRenaming(false)} />}
    </div>
  );
}

function CameraView({ camera }: { camera: CameraRead }) {
  const images = useCameraImages(camera.id);
  const { current, index, select } = useSelectedImage(images.images);
  const zones = useZones(camera.id);

  if (images.isPending) return <Loading />;
  if (images.error) return <ErrorBox error={images.error} />;
  if (images.total === 0 || !current) {
    return <Empty icon="image" title="У камеры нет снимков">Загрузите их — экран покажет кадр, зоны и рамки.</Empty>;
  }
  return (
    <div className="space-y-3">
      <ImagePicker images={images.images} current={current} index={index} onSelect={select} />
      {images.truncated && (
        <p className="text-xs text-muted">
          Показаны последние {images.images.length} снимков из {images.total}.
        </p>
      )}
      <ImagePanel imageId={current.id} camera={camera} zones={zones.data?.items ?? []} zonesError={zones.error} />
    </div>
  );
}

/** Снимки по дням: сначала день, потом время. ← и → листают подряд через дни. */
function ImagePicker({
  images,
  current,
  index,
  onSelect,
}: {
  images: ImageRead[];
  current: ImageRead;
  index: number;
  onSelect: (image: ImageRead) => void;
}) {
  const days = groupByDay(images);
  const currentDay = dayOf(current);
  const step = (delta: number) => {
    const next = images[index + delta];
    if (next) onSelect(next);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input, textarea, select")) return;
      if (e.key === "ArrowLeft") step(-1);
      if (e.key === "ArrowRight") step(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div className="space-y-2.5 rounded-2xl bg-white p-3 shadow-sm ring-1 ring-ink/[0.07]">
      <div className="flex items-center gap-2">
        <IconButton icon="chevronLeft" label="Предыдущий снимок (←)" size="sm" onClick={() => step(-1)} disabled={index === 0} />
        <div className="flex flex-1 flex-wrap gap-1">
          {[...days.keys()].map((day) => (
            <button
              key={day}
              type="button"
              onClick={() => {
                const first = days.get(day)?.[0];
                if (first) onSelect(first);
              }}
              className={`h-8 rounded-lg px-2.5 text-sm font-medium tabular-nums ${day === currentDay ? "bg-ink text-white" : "text-ink/70 hover:bg-ink/[0.06]"}`}
            >
              {day}
            </button>
          ))}
        </div>
        <span className="text-xs tabular-nums text-muted">
          {index + 1} / {images.length}
        </span>
        <IconButton icon="chevronRight" label="Следующий снимок (→)" size="sm" onClick={() => step(1)} disabled={index === images.length - 1} />
      </div>
      <div className="flex flex-wrap gap-1 border-t border-ink/[0.06] pt-2.5">
        {(days.get(currentDay) ?? []).map((image) => (
          <button
            key={image.id}
            type="button"
            onClick={() => onSelect(image)}
            title={label(ru.imageStatus, image.status)}
            className={`h-7 rounded-md px-2 text-[13px] tabular-nums ${
              image.id === current.id ? "bg-accent font-medium text-white" : "text-ink/75 hover:bg-ink/[0.06]"
            } ${image.usable === false ? "line-through opacity-60" : ""}`}
          >
            {timeOf(image)}
          </button>
        ))}
      </div>
    </div>
  );
}

function ImagePanel({
  imageId,
  camera,
  zones,
  zonesError,
}: {
  imageId: string;
  camera: CameraRead;
  zones: ZoneRead[];
  zonesError: unknown;
}) {
  const image = useImage(imageId);
  const classes = useQuery(equipmentClassesQuery);
  const [showZones, setShowZones] = useState(true);
  // Скрытые классы переживают переход к другому снимку: людей на обзорной камере десятки.
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  if (image.isPending) return <Loading />;
  if (image.isError) return <ErrorBox error={image.error} onRetry={() => image.refetch()} />;
  const detail = image.data;
  const size = { width: detail.width ?? 1920, height: detail.height ?? 1080 };
  const zoneById = new Map(zones.map((z) => [z.id, z]));
  const className = (code: string) => classes.data?.get(code) ?? code;
  const counts = countByClass(detail.detections);
  const shown = detail.detections.filter((d) => !hidden.has(d.equipment_class));
  const toggle = (code: string) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  const chip = (active: boolean) =>
    `inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-[13px] ring-1 transition-colors ${
      active ? "bg-white text-ink ring-ink/20" : "bg-transparent text-muted line-through ring-transparent hover:ring-ink/10"
    }`;

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="space-y-2">
        <Frame url={detail.url} alt={`Снимок ${formatMoment(detail.captured_at)}`} {...size}>
          {showZones &&
            zones.map((zone) => (
              <ZoneOutline
                key={zone.id}
                polygon={zonePolygon(zone)}
                color={zoneColor(zone.zone_type)}
                label={zone.name}
                size={size}
                muted={shown.length > 0}
              />
            ))}
          {shown.map((d) => (
            <DetectionBox
              key={d.id}
              bbox={d.bbox}
              anchor={d.anchor}
              label={`${className(d.equipment_class)} ${d.conf.toFixed(2)}`}
              color={DETECTION_COLOR}
              size={size}
            />
          ))}
        </Frame>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-xs text-muted">Показать:</span>
          <button type="button" onClick={() => setShowZones((v) => !v)} className={chip(showZones)}>
            <Icon name="zones" size={13} />
            зоны
          </button>
          {[...counts].map(([code, count]) => (
            <button key={code} type="button" onClick={() => toggle(code)} className={chip(!hidden.has(code))}>
              {className(code)} <b className="tabular-nums">{count}</b>
            </button>
          ))}
        </div>
        {zonesError != null && <ErrorBox error={zonesError} />}
      </div>
      <ImageSide detail={detail} camera={camera} zoneById={zoneById} className={className} />
    </div>
  );
}

function ImageSide({
  detail,
  camera,
  zoneById,
  className,
}: {
  detail: ImageDetail;
  camera: CameraRead;
  zoneById: Map<string, ZoneRead>;
  className: (code: string) => string;
}) {
  const quality = detail.quality as { brightness?: number; blur?: number };
  return (
    <Panel bodyClassName="p-4 space-y-4 text-sm">
      <div className="space-y-1.5">
        <p className="flex items-center gap-2 font-semibold">
          <Icon name="clock" size={15} className="text-muted" />
          {formatMoment(detail.captured_at)}
        </p>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="bg-ink/[0.06] text-ink/75" size="sm">
            {label(ru.imageStatus, detail.status)}
          </Badge>
          {detail.usable === false && (
            <Badge tone="bg-red-50 text-red-800 ring-1 ring-inset ring-red-600/20" size="sm">
              непригоден: {detail.usable_reason ?? "?"}
            </Badge>
          )}
          {detail.stage && (
            <Badge tone="bg-sky-50 text-sky-800 ring-1 ring-inset ring-sky-600/20" size="sm">
              стадия: {label(ru.stageLabel as Record<string, string>, detail.stage.stage_label)} ({detail.stage.conf.toFixed(2)})
            </Badge>
          )}
        </div>
        {typeof quality.brightness === "number" && (
          <p className="text-xs text-muted">
            яркость {quality.brightness.toFixed(2)}, размытость {quality.blur?.toFixed(2) ?? "—"}
          </p>
        )}
        <ReferenceControl imageId={detail.id} camera={camera} />
      </div>
      <div>
        <p className="mb-1.5 font-medium">Техника на снимке: {detail.detections.length}</p>
        {detail.detections.length === 0 ? (
          <p className="text-muted">
            {detail.status === "ANALYZED" ? "Распознавание техники не нашло." : "Снимок ещё не распознан."}
          </p>
        ) : (
          <ul className="max-h-[28rem] divide-y divide-ink/[0.06] overflow-y-auto">
            {detail.detections.map((d) => {
              const zone = d.zone_id ? zoneById.get(d.zone_id) : undefined;
              return (
                <li key={d.id} className="py-1.5">
                  <span className="font-medium">{className(d.equipment_class)}</span>{" "}
                  <span className="text-xs tabular-nums text-muted">{d.conf.toFixed(2)}</span>
                  <span className="block text-xs text-muted">
                    {zone ? (
                      <span style={{ color: zoneColor(zone.zone_type) }}>
                        {zone.name} ({isZoneType(zone.zone_type) ? ru.zoneType[zone.zone_type] : zone.zone_type})
                      </span>
                    ) : (
                      "вне зон"
                    )}
                    {" · "}
                    {movement(d.moved)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Panel>
  );
}

function ReferenceControl({ imageId, camera }: { imageId: string; camera: CameraRead }) {
  const setReference = useSetReference(camera);
  const toast = useToast();
  if (camera.reference_image_id === imageId) {
    return (
      <p className="flex items-center gap-1.5 text-xs font-medium text-accent">
        <Icon name="check" size={13} />
        Эталонный кадр камеры: на нём размечают зоны
      </p>
    );
  }
  return (
    <Button
      size="sm"
      variant="ghost"
      icon="image"
      loading={setReference.isPending}
      className="-ml-2.5"
      onClick={() =>
        setReference.mutate(imageId, {
          onSuccess: () => toast.success("Эталонный кадр выбран", "На нём теперь размечают зоны камеры"),
          onError: (error) => toast.error(error),
        })
      }
    >
      Сделать эталонным кадром
    </Button>
  );
}

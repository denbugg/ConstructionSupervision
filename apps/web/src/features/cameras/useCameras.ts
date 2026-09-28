import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { formatMoment } from "@/entities/format";
import type { Point } from "@/entities/polygon";
import { apiGet, apiPatch, apiPost } from "@/shared/api/client";
import {
  camerasQuery,
  imageQuery,
  zonesQuery,
  type CameraRead,
  type ImageRead,
  type ZoneRead,
} from "@/shared/api/queries";
import type { SiteSchema } from "@/shared/api/schemas";

/** Сколько снимков камеры держит экран: список идёт по времени, берём хвост. */
const IMAGES_LIMIT = 200;

/**
 * Выбранная камера — в адресе (`?camera=<код>`): ссылку на камеру можно переслать. Без
 * параметра — первая активная камера объекта.
 */
export function useSelectedCamera(objectId: string) {
  const [params, setParams] = useSearchParams();
  const cameras = useQuery(camerasQuery(objectId));
  const items = cameras.data?.items ?? [];
  const code = params.get("camera");
  const camera = items.find((c) => c.code === code) ?? items.find((c) => c.is_active) ?? items[0];
  const select = (next: CameraRead) =>
    setParams((p) => {
      p.set("camera", next.code);
      p.delete("image");
      return p;
    });
  return { cameras, items, camera, select };
}

/**
 * Снимки камеры по времени съёмки. Список отдаётся по возрастанию, поэтому сначала берётся
 * общее число, потом хвост: при большом архиве на экране последние IMAGES_LIMIT снимков.
 */
export function useCameraImages(cameraId: string | undefined) {
  const base = `/site/images?camera_id=${cameraId}`;
  const count = useQuery({
    queryKey: ["site", "images", "camera", cameraId, "count"],
    enabled: cameraId != null,
    queryFn: ({ signal }) => apiGet<SiteSchema<"Page_ImageRead_">>(`${base}&limit=1`, signal),
  });
  const total = count.data?.total ?? 0;
  const offset = Math.max(0, total - IMAGES_LIMIT);
  const list = useQuery({
    queryKey: ["site", "images", "camera", cameraId, "tail", total],
    enabled: cameraId != null && total > 0,
    queryFn: ({ signal }) =>
      apiGet<SiteSchema<"Page_ImageRead_">>(`${base}&limit=${IMAGES_LIMIT}&offset=${offset}`, signal),
  });
  return {
    isPending: count.isPending || (total > 0 && list.isPending),
    error: count.error ?? list.error,
    total,
    truncated: offset > 0,
    images: list.data?.items ?? [],
  };
}

/** Выбранный снимок — в адресе (`?image=<id>`); по умолчанию последний. */
export function useSelectedImage(images: ImageRead[]) {
  const [params, setParams] = useSearchParams();
  const id = params.get("image");
  const index = Math.max(
    0,
    id ? images.findIndex((i) => i.id === id) : images.length - 1,
  );
  const select = (image: ImageRead) =>
    setParams((p) => {
      p.set("image", image.id);
      return p;
    });
  const current = images[index] as ImageRead | undefined;
  return { current, index, select };
}

export function useImage(imageId: string | null | undefined) {
  return useQuery({ ...imageQuery(imageId ?? ""), enabled: imageId != null });
}

export function useZones(cameraId: string | undefined) {
  return useQuery({ ...zonesQuery(cameraId ?? ""), enabled: cameraId != null });
}

/** Полигон зоны из API в виде точек редактора. */
export function zonePolygon(zone: ZoneRead): Point[] {
  return zone.polygon.map(([x, y]) => [x, y] as Point);
}

/** День снимка по Москве: «20.10.2026». */
export function dayOf(image: ImageRead): string {
  return formatMoment(image.captured_at).split(",")[0] ?? "—";
}

/** Время снимка по Москве: «09:35». */
export function timeOf(image: ImageRead): string {
  return formatMoment(image.captured_at).split(", ")[1] ?? "—";
}

/** Снимки по дням в порядке списка (он уже идёт по времени съёмки). */
export function groupByDay(images: ImageRead[]): Map<string, ImageRead[]> {
  const days = new Map<string, ImageRead[]>();
  for (const image of images) {
    const day = dayOf(image);
    days.set(day, [...(days.get(day) ?? []), image]);
  }
  return days;
}

/** Число рамок по классам в порядке первого появления: подписи переключателей на экране. */
export function countByClass(detections: { equipment_class: string }[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const d of detections) counts.set(d.equipment_class, (counts.get(d.equipment_class) ?? 0) + 1);
  return counts;
}

/**
 * Точки контакта техники со всех снимков камеры — где машины стояли на самом деле. Нужны
 * редактору зон: граница участка проводится по этим точкам, а не на глаз. Загружаются по
 * запросу: это карточка на каждый снимок камеры.
 */
export function useCameraAnchors(cameraId: string, enabled: boolean) {
  const images = useCameraImages(enabled ? cameraId : undefined);
  const details = useQueries({
    queries: images.images.map((image) => ({ ...imageQuery(image.id), enabled })),
  });
  return {
    isPending: enabled && (images.isPending || details.some((d) => d.isPending)),
    error: images.error ?? details.find((d) => d.error)?.error ?? null,
    anchors: details.flatMap((d) =>
      (d.data?.detections ?? []).map((det) => ({
        id: det.id,
        equipmentClass: det.equipment_class,
        point: [det.anchor[0] ?? 0, det.anchor[1] ?? 0] as Point,
      })),
    ),
  };
}

/** Смещение с прошлого окна словами; `null` — прошлого окна у камеры нет, сравнивать не с чем. */
export function movement(moved: boolean | null | undefined): string {
  if (moved === true) return "сдвинулась с прошлого окна";
  if (moved === false) return "стоит на месте";
  return "прошлого окна нет";
}

/** Сделать снимок эталонным кадром камеры: на нём размечают зоны. */
export function useSetReference(camera: CameraRead) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (imageId: string) =>
      apiPatch<CameraRead>(`/site/cameras/${camera.id}`, { reference_image_id: imageId }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["site", "cameras"] }),
  });
}

/** Завести камеру заранее, до снимков: код — он же имя папки при загрузке. */
export function useCreateCamera(objectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ code, name }: { code: string; name: string }) =>
      apiPost<CameraRead>("/site/cameras", { object_id: objectId, code, name: name.trim() || null }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["site", "cameras"] }),
  });
}

/**
 * Название и активность камеры. Выключение гасит и её зоны, а факты окон объекта
 * пересчитываются в фоне: участок, который видела только она, станет слепым.
 */
export function useUpdateCamera(camera: CameraRead) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (fields: { name?: string; is_active?: boolean }) =>
      apiPatch<CameraRead>(`/site/cameras/${camera.id}`, fields),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: ["site"] }),
        client.invalidateQueries({ queryKey: ["analysis"] }),
      ]),
  });
}

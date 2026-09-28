import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { batches, uploadName, type Picked } from "@/features/upload/files";
import { apiGet, apiPatch, apiPost, apiUpload } from "@/shared/api/client";
import { imageCountQuery, type ImageRead } from "@/shared/api/queries";
import type { SiteSchema } from "@/shared/api/schemas";

export type IntakeResult = SiteSchema<"IntakeResult">;

/** Куда относить снимки: по подпапкам (папка = код камеры) или все — в одну камеру. */
export type CameraTarget = { kind: "folders"; stripParent: boolean } | { kind: "camera"; code: string };

export type UploadRequest = {
  picked: Picked[];
  target: CameraTarget;
  /** Время для файлов, где его нет ни в EXIF, ни в имени; ISO-8601 со смещением Москвы. */
  capturedAt: string | null;
};

export type UploadProgress = { batch: number; batches: number; share: number };

/**
 * Пакетная загрузка: запросы по 200 файлов подряд, прогресс — по байтам текущего пакета.
 * Ответ сервиса — частичный успех, поэтому принятые и отклонённые копятся по всем пакетам.
 */
export function useUploadImages(objectId: string) {
  const client = useQueryClient();
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const mutation = useMutation({
    mutationFn: async ({ picked, target, capturedAt }: UploadRequest): Promise<IntakeResult> => {
      const parts = batches(picked);
      const total: IntakeResult = { accepted: [], rejected: [] };
      for (const [index, part] of parts.entries()) {
        const form = new FormData();
        form.append("object_id", objectId);
        if (target.kind === "camera") form.append("camera_code", target.code);
        if (capturedAt) form.append("captured_at", capturedAt);
        for (const p of part) {
          const name = target.kind === "camera" ? p.file.name : uploadName(p, target.stripParent);
          form.append("files", p.file, name);
        }
        const result = await apiUpload<IntakeResult>("/site/images", form, (share) =>
          setProgress({ batch: index + 1, batches: parts.length, share }),
        );
        total.accepted.push(...result.accepted);
        total.rejected.push(...result.rejected);
      }
      return total;
    },
    onSettled: () => {
      setProgress(null);
      return client.invalidateQueries({ queryKey: ["site"] });
    },
  });
  return { ...mutation, progress };
}

export const PIPELINE = ["PENDING", "PROCESSING", "ANALYZED", "FAILED", "NEEDS_TIME"] as const;
export type PipelineStatus = (typeof PIPELINE)[number];

/**
 * Очередь распознавания по статусам. Пока есть ждущие и распознаваемые снимки, счётчики
 * перечитываются каждые 3 секунды; когда очередь опустела — обновляются выводы анализа:
 * site сам сигналит analysis о новых фактах.
 */
export function usePipeline(objectId: string) {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const counts = useQueries({
    queries: PIPELINE.map((status) => ({
      ...imageCountQuery(objectId, status),
      refetchInterval: busy ? 3000 : (false as const),
    })),
  });
  const value = (status: PipelineStatus) => counts[PIPELINE.indexOf(status)]?.data ?? 0;
  const inFlight = value("PENDING") + value("PROCESSING");
  const wasBusy = useRef(false);

  useEffect(() => {
    setBusy(inFlight > 0);
    if (wasBusy.current && inFlight === 0) {
      void client.invalidateQueries({ queryKey: ["analysis"] });
      void client.invalidateQueries({ queryKey: ["site", "images"] });
    }
    wasBusy.current = inFlight > 0;
  }, [inFlight, client]);

  return {
    isPending: counts.some((c) => c.isPending),
    error: counts.find((c) => c.error)?.error ?? null,
    value,
    inFlight,
    total: PIPELINE.reduce((sum, s) => sum + value(s), 0),
  };
}

/** Распознать снимки объекта заново — после смены модели или порога. */
export function useReanalyze(objectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (cameraId?: string) =>
      apiPost<SiteSchema<"ReanalyzeResult">>("/site/images/reanalyze", {
        object_id: objectId,
        camera_id: cameraId ?? null,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["site", "images"] }),
  });
}

// Снимков без времени на экране — одна страница: их правят руками, сотни тут не ждут.
const NEEDS_TIME_PAGE = 50;

/** Снимки без времени съёмки: ждут, пока оператор укажет время вручную. */
export function useNeedsTime(objectId: string) {
  return useQuery({
    queryKey: ["site", "images", objectId, "needs-time"],
    queryFn: ({ signal }) =>
      apiGet<SiteSchema<"Page_ImageRead_">>(
        `/site/images?object_id=${objectId}&status=NEEDS_TIME&limit=${NEEDS_TIME_PAGE}`,
        signal,
      ),
  });
}

/**
 * Время съёмки вручную. Поле формы — местное время Москвы; смещение пишем явно, чтобы
 * сервер не толковал его по поясу камеры (`CAMERA_TIMEZONE`).
 */
export function useSetImageTime() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ image, local }: { image: ImageRead; local: string }) =>
      apiPatch<ImageRead>(`/site/images/${image.id}`, { captured_at: `${local}:00+03:00` }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["site", "images"] }),
  });
}

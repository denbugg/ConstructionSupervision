import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useReducer, useState } from "react";

import { changes, fromServer, reducer, type Change } from "@/features/zones-editor/draft";
import { ApiError, apiDelete, apiPatch, apiPost } from "@/shared/api/client";
import { areasQuery, zonesQuery, type CameraRead, type ZoneRead } from "@/shared/api/queries";

type Outcome = { key: string; zone: ZoneRead | null } | { key: string; error: unknown };

/**
 * Разметка камеры: зоны с сервера, локальный черновик правок и их сохранение. Черновик
 * пересобирается из ответа сервера, когда тот меняется: после полного сохранения и при
 * смене камеры.
 */
export function useZonesEditor(camera: CameraRead) {
  const zones = useQuery(zonesQuery(camera.id));
  const [draft, dispatch] = useReducer(reducer, [], fromServer);
  const client = useQueryClient();
  const [errors, setErrors] = useState<Map<string, unknown>>(new Map());

  useEffect(() => {
    if (zones.data) dispatch({ type: "reset", zones: zones.data.items });
  }, [zones.data]);

  const pending = changes(draft);

  const save = useMutation({
    mutationFn: () => saveChanges(camera.id, pending),
    onSuccess: async (outcomes) => {
      const failed = new Map<string, unknown>();
      for (const outcome of outcomes) {
        if ("error" in outcome) failed.set(outcome.key, outcome.error);
        else dispatch({ type: "committed", key: outcome.key, zone: outcome.zone });
      }
      setErrors(failed);
      // При частичном успехе черновик не перечитывается с сервера: несохранённые правки
      // остались бы потерянными. Сохранённые уже отмечены в черновике выше.
      if (failed.size === 0) {
        await client.invalidateQueries({ queryKey: zonesQuery(camera.id).queryKey });
      }
      await client.invalidateQueries({ queryKey: areasQuery(camera.object_id).queryKey });
    },
  });

  const discard = () => {
    setErrors(new Map());
    dispatch({ type: "reset", zones: zones.data?.items ?? [] });
  };

  return { zones, draft, dispatch, pending, save, errors, discard };
}

/**
 * Правки по одной, по порядку: сначала удаления, потом правки и новые зоны. Ошибка одной
 * зоны не останавливает остальные — оператор увидит, какая зона не сохранилась и почему.
 */
async function saveChanges(cameraId: string, pending: Change[]): Promise<Outcome[]> {
  const order = { delete: 0, update: 1, create: 2 };
  const outcomes: Outcome[] = [];
  for (const change of [...pending].sort((a, b) => order[a.kind] - order[b.kind])) {
    try {
      outcomes.push({ key: change.zone.key, zone: await send(cameraId, change) });
    } catch (error) {
      outcomes.push({ key: change.zone.key, error });
    }
  }
  return outcomes;
}

async function send(cameraId: string, change: Change): Promise<ZoneRead | null> {
  const { zone } = change;
  switch (change.kind) {
    case "delete":
      await apiDelete(`/site/zones/${zone.id}`);
      return null;
    case "update":
      return apiPatch<ZoneRead>(`/site/zones/${zone.id}`, change.fields);
    case "create":
      return apiPost<ZoneRead>("/site/zones", {
        camera_id: cameraId,
        zone_type: zone.zoneType,
        name: zone.name.trim() || null,
        polygon: zone.polygon,
      });
  }
}

/** Текст ошибки сохранения зоны — тот `message`, что вернул сервис. */
export function saveErrorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

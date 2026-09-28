import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createBody, updateBody, type ObjectDraft } from "@/features/objects/objectDraft";
import { apiDelete, apiPatch, apiPost, apiPostForm } from "@/shared/api/client";
import type { ObjectRead } from "@/shared/api/queries";
import type { PlanSchema } from "@/shared/api/schemas";

export type GenerateResult = PlanSchema<"PlanGenerateResult">;
export type ImportResult = PlanSchema<"PlanImportResult">;

/** Откуда взять график нового объекта: по нормам, из файла или позже. */
export type ScheduleSource = { kind: "generate" } | { kind: "import"; file: File } | { kind: "later" };

/**
 * Создание объекта и сразу его графика. Шаги отдельные: объект создаётся, даже если график
 * не построился, — тогда `scheduleError` объясняет почему, а объект открыт для правки.
 */
export function useCreateObject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ draft, schedule }: { draft: ObjectDraft; schedule: ScheduleSource }) => {
      const object = await apiPost<ObjectRead>("/plan/objects", createBody(draft));
      let scheduleError: unknown = null;
      try {
        if (schedule.kind === "generate") await generatePlan(object.id, {}, false);
        if (schedule.kind === "import") await importPlan(object.id, schedule.file, false);
      } catch (error) {
        scheduleError = error;
      }
      return { object, scheduleError };
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["plan"] }),
  });
}

export function useUpdateObject(object: ObjectRead) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (draft: ObjectDraft) =>
      apiPatch<ObjectRead>(`/plan/objects/${object.id}`, updateBody(draft, object)),
    onSuccess: () => client.invalidateQueries({ queryKey: ["plan"] }),
  });
}

/** В архив — `DELETE`: объект не удаляется, выводы и снимки остаются (plan-service README). */
export function useArchiveObject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (objectId: string) => apiDelete(`/plan/objects/${objectId}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["plan"] }),
  });
}

/** Из архива — обратно в работу. */
export function useRestoreObject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (objectId: string) =>
      apiPatch<ObjectRead>(`/plan/objects/${objectId}`, { status: "ACTIVE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["plan"] }),
  });
}

/** Генерация графика по МРР; параметры из запроса дополняют и сохраняют `tep` объекта. */
export function generatePlan(
  objectId: string,
  body: PlanSchema<"PlanGenerateRequest">,
  force: boolean,
): Promise<GenerateResult> {
  return apiPost<GenerateResult>(`/plan/objects/${objectId}/plan/generate?force=${force}`, body);
}

export function importPlan(objectId: string, file: File, force: boolean): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<ImportResult>(`/plan/objects/${objectId}/plan/import?force=${force}`, form);
}

/** После замены графика устаревает всё: этапы, правила, прогресс и лента. */
export function useScheduleInvalidation() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: ["plan"] }),
      client.invalidateQueries({ queryKey: ["analysis"] }),
    ]);
}

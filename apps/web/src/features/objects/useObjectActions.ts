import { useArchiveObject, useRestoreObject } from "@/features/objects/useObjects";
import type { ObjectRead } from "@/shared/api/queries";
import { useConfirm } from "@/shared/ui/Modal";
import { useToast } from "@/shared/ui/Toast";

/**
 * Архив и возврат объекта с подтверждением и уведомлением — одинаково из списка объектов и
 * из меню открытого объекта.
 */
export function useObjectActions() {
  const confirm = useConfirm();
  const toast = useToast();
  const archive = useArchiveObject();
  const restore = useRestoreObject();

  return {
    busy: archive.isPending || restore.isPending,
    archive: async (object: ObjectRead, onDone?: () => void) => {
      const ok = await confirm({
        title: `Перевести в архив «${object.name}»?`,
        message:
          "Объект пропадёт из списка действующих. Снимки, выводы и отчёты сохранятся; вернуть объект в работу можно в любой момент.",
        confirmLabel: "В архив",
        tone: "danger",
      });
      if (!ok) return;
      archive.mutate(object.id, {
        onSuccess: () => {
          toast.success("Объект в архиве", object.name);
          onDone?.();
        },
        onError: (error) => toast.error(error, "Не удалось перевести в архив"),
      });
    },
    restore: (object: ObjectRead) =>
      restore.mutate(object.id, {
        onSuccess: () => toast.success("Объект снова в работе", object.name),
        onError: (error) => toast.error(error, "Не удалось вернуть из архива"),
      }),
  };
}

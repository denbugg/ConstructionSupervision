import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { RequisiteFields, TepFields } from "@/features/objects/ObjectFields";
import {
  draftFromObject,
  draftProblems,
  type Lifecycle,
  type ObjectDraft,
} from "@/features/objects/objectDraft";
import { useCreateObject, useUpdateObject, type ScheduleSource } from "@/features/objects/useObjects";
import type { ObjectRead } from "@/shared/api/queries";
import { ru } from "@/shared/locale/ru";
import { Button } from "@/shared/ui/Button";
import { Field, selectClass } from "@/shared/ui/Field";
import { Icon, type IconName } from "@/shared/ui/Icon";
import { Modal } from "@/shared/ui/Modal";
import { ErrorBox, errorText } from "@/shared/ui/QueryState";
import { useToast } from "@/shared/ui/Toast";

type Source = ScheduleSource["kind"];

const SOURCES: { kind: Source; icon: IconName; title: string; text: string }[] = [
  {
    kind: "generate",
    icon: "sparkle",
    title: "По нормам МРР",
    text: "Этапы, сроки и правила техники — по МРР-3.2.81-12 из этажности и площади",
  },
  { kind: "import", icon: "upload", title: "Из файла", text: "CSV или XLSX: код, название, начало, окончание" },
  { kind: "later", icon: "clock", title: "Позже", text: "Объект без графика; построить можно в настройках" },
];

/**
 * Новый объект за один шаг: реквизиты, параметры и откуда взять график. После создания
 * сразу открывается объект — дальше чек-лист на его обзоре подскажет, что загрузить.
 */
export function CreateObjectDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [draft, setDraft] = useState<ObjectDraft>(() => draftFromObject());
  const [source, setSource] = useState<Source>("generate");
  const [file, setFile] = useState<File | null>(null);
  const [tried, setTried] = useState(false);
  const create = useCreateObject();
  const toast = useToast();
  const navigate = useNavigate();

  const problems = draftProblems(draft, source === "generate");
  const fileMissing = source === "import" && file == null;
  const close = () => {
    onClose();
    setDraft(draftFromObject());
    setFile(null);
    setTried(false);
    create.reset();
  };

  const submit = () => {
    setTried(true);
    if (Object.keys(problems).length > 0 || fileMissing) return;
    const schedule: ScheduleSource =
      source === "import" && file ? { kind: "import", file } : source === "generate" ? { kind: "generate" } : { kind: "later" };
    create.mutate(
      { draft, schedule },
      {
        onSuccess: ({ object, scheduleError }) => {
          close();
          if (scheduleError) {
            toast.error(scheduleError, "Объект создан, но график не построен");
            navigate(`/objects/${object.id}/settings`);
          } else {
            toast.success("Объект создан", source === "later" ? "График можно построить в настройках объекта" : "График построен");
            navigate(`/objects/${object.id}`);
          }
        },
      },
    );
  };

  const shown = tried ? problems : {};
  return (
    <Modal
      open={open}
      onClose={close}
      title="Новый объект"
      description="Реквизиты, параметры и график. Камеры появятся сами при загрузке снимков."
      size="lg"
      busy={create.isPending}
      onSubmit={submit}
      footer={
        <>
          <Button variant="ghost" onClick={close} disabled={create.isPending}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" icon="check" loading={create.isPending}>
            {create.isPending ? "Создаём…" : "Создать объект"}
          </Button>
        </>
      }
    >
      <div className="space-y-6">
        <RequisiteFields draft={draft} problems={shown} onChange={setDraft} />

        <div className="space-y-2.5">
          <p className="text-[13px] font-medium text-ink/85">График работ</p>
          <div className="grid gap-2 sm:grid-cols-3">
            {SOURCES.map((option) => (
              <button
                key={option.kind}
                type="button"
                onClick={() => setSource(option.kind)}
                aria-pressed={source === option.kind}
                className={`rounded-xl p-3 text-left ring-1 transition ${
                  source === option.kind ? "bg-accent/[0.06] ring-2 ring-accent" : "ring-ink/15 hover:ring-ink/30"
                }`}
              >
                <span className="flex items-center gap-2 font-medium">
                  <Icon name={option.icon} size={16} className={source === option.kind ? "text-accent" : "text-muted"} />
                  {option.title}
                </span>
                <span className="mt-1 block text-xs text-muted">{option.text}</span>
              </button>
            ))}
          </div>
          {source === "import" && (
            <Field label="Файл графика" error={tried && fileMissing ? "Выберите файл" : null}>
              <input
                type="file"
                accept=".csv,.xlsx"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-ink file:px-3 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-ink/85"
              />
            </Field>
          )}
        </div>

        <div className="space-y-2.5">
          <p className="text-[13px] font-medium text-ink/85">
            Параметры объекта (ТЭП){source === "generate" && <span className="text-accent"> — нужны для генерации</span>}
          </p>
          <TepFields tep={draft.tep} problems={shown} onChange={(tep) => setDraft({ ...draft, tep })} />
        </div>

        {create.isError && <ErrorBox error={create.error} />}
      </div>
    </Modal>
  );
}

const LIFECYCLE: Lifecycle[] = ["DRAFT", "ACTIVE"];

/** Правка реквизитов и параметров. График сам не перестраивается: это отдельное действие. */
export function EditObjectDialog({
  object,
  open,
  onClose,
}: {
  object: ObjectRead;
  open: boolean;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<ObjectDraft>(() => draftFromObject(object));
  const update = useUpdateObject(object);
  const toast = useToast();
  const problems = draftProblems(draft, false);

  const submit = () => {
    if (Object.keys(problems).length > 0) return;
    update.mutate(draft, {
      onSuccess: () => {
        toast.success("Реквизиты сохранены");
        onClose();
      },
    });
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Реквизиты объекта"
      description="Параметры ТЭП сохраняются в объекте; график по ним перестраивается в настройках."
      size="lg"
      busy={update.isPending}
      onSubmit={submit}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={update.isPending}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" icon="check" loading={update.isPending} disabled={Object.keys(problems).length > 0}>
            Сохранить
          </Button>
        </>
      }
    >
      <div className="space-y-6">
        <RequisiteFields draft={draft} problems={problems} onChange={setDraft} />
        {object.status !== "ARCHIVED" && (
          <Field label="Состояние" hint="В архив — отдельным действием, из меню объекта" className="max-w-xs">
            <select
              value={draft.status}
              onChange={(e) => setDraft({ ...draft, status: e.target.value as Lifecycle })}
              className={selectClass}
            >
              {LIFECYCLE.map((s) => (
                <option key={s} value={s}>
                  {ru.objectLifecycle[s]}
                </option>
              ))}
            </select>
          </Field>
        )}
        <div className="space-y-2.5">
          <p className="text-[13px] font-medium text-ink/85">Параметры объекта (ТЭП)</p>
          <TepFields tep={draft.tep} problems={problems} onChange={(tep) => setDraft({ ...draft, tep })} />
        </div>
        {update.isError && <p className="text-sm text-red-700">{errorText(update.error)}</p>}
      </div>
    </Modal>
  );
}

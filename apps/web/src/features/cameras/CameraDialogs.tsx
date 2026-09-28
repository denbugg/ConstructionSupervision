import { useState } from "react";

import { useCreateCamera, useUpdateCamera } from "@/features/cameras/useCameras";
import type { CameraRead } from "@/shared/api/queries";
import { Button } from "@/shared/ui/Button";
import { Field, inputClass } from "@/shared/ui/Field";
import { Modal } from "@/shared/ui/Modal";
import { ErrorBox } from "@/shared/ui/QueryState";
import { useToast } from "@/shared/ui/Toast";

/** Новая камера до первых снимков: чтобы загружать в неё файлы без папки. */
export function CreateCameraDialog({
  objectId,
  onClose,
  onCreated,
}: {
  objectId: string;
  onClose: () => void;
  onCreated: (camera: CameraRead) => void;
}) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const create = useCreateCamera(objectId);
  const toast = useToast();
  const submit = () =>
    code.trim() &&
    create.mutate(
      { code: code.trim(), name },
      {
        onSuccess: (camera) => {
          toast.success("Камера заведена", camera.name);
          onCreated(camera);
          onClose();
        },
      },
    );
  return (
    <Modal
      open
      onClose={onClose}
      title="Новая камера"
      description="Обычно камеры заводятся сами — по папкам при загрузке снимков. Вручную — если снимки придут без папок."
      size="sm"
      busy={create.isPending}
      onSubmit={submit}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" icon="plus" loading={create.isPending} disabled={!code.trim()}>
            Завести
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Код" required hint="Он же имя папки при загрузке; не меняется. Латиница, цифры, «-», «_», «.»">
          <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="cam-north" className={inputClass} />
        </Field>
        <Field label="Название" hint="По умолчанию — код">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Северная, над въездом" className={inputClass} />
        </Field>
        {create.isError && <ErrorBox error={create.error} />}
      </div>
    </Modal>
  );
}

export function RenameCameraDialog({ camera, onClose }: { camera: CameraRead; onClose: () => void }) {
  const [name, setName] = useState(camera.name);
  const update = useUpdateCamera(camera);
  const toast = useToast();
  const submit = () =>
    name.trim() &&
    update.mutate(
      { name: name.trim() },
      {
        onSuccess: () => {
          toast.success("Камера переименована");
          onClose();
        },
      },
    );
  return (
    <Modal
      open
      onClose={onClose}
      title="Название камеры"
      description={`Код «${camera.code}» не меняется: по нему снимки раскладываются по камерам.`}
      size="sm"
      busy={update.isPending}
      onSubmit={submit}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" icon="check" loading={update.isPending} disabled={!name.trim()}>
            Сохранить
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Название">
          <input value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
        </Field>
        {update.isError && <ErrorBox error={update.error} />}
      </div>
    </Modal>
  );
}

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { formatMoment } from "@/entities/format";
import {
  PIPELINE,
  useNeedsTime,
  usePipeline,
  useReanalyze,
  useSetImageTime,
  type PipelineStatus,
} from "@/features/upload/useUpload";
import { camerasQuery, imageQuery, type ImageRead } from "@/shared/api/queries";
import { label, ru } from "@/shared/locale/ru";
import { Dot } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { fieldClass } from "@/shared/ui/Field";
import { useConfirm } from "@/shared/ui/Modal";
import { Panel } from "@/shared/ui/Page";
import { ErrorBox, Loading, Spinner } from "@/shared/ui/QueryState";
import { useToast } from "@/shared/ui/Toast";

const DOT: Record<PipelineStatus, string> = {
  PENDING: "bg-stone-400",
  PROCESSING: "bg-sky-500",
  ANALYZED: "bg-emerald-500",
  FAILED: "bg-red-600",
  NEEDS_TIME: "bg-amber-500",
};

/** Очередь распознавания: сколько снимков в каком статусе; пока идёт — обновляется сама. */
export function PipelinePanel({ objectId }: { objectId: string }) {
  const pipeline = usePipeline(objectId);
  const reanalyze = useReanalyze(objectId);
  const confirm = useConfirm();
  const toast = useToast();
  const analyzed = pipeline.value("ANALYZED");
  const share = pipeline.total > 0 ? (analyzed / pipeline.total) * 100 : 0;

  const rerun = async () => {
    const ok = await confirm({
      title: "Распознать все снимки заново?",
      message:
        "Нужно после смены модели или её порога. Распознанные и отказные снимки снова встанут в очередь; факты и выводы пересчитаются по мере распознавания — это займёт время.",
      confirmLabel: "Распознать заново",
    });
    if (!ok) return;
    reanalyze.mutate(undefined, {
      onSuccess: (result) => toast.success(`В очереди снова: ${result.images} снимков`),
      onError: (error) => toast.error(error, "Не удалось поставить в очередь"),
    });
  };

  return (
    <Panel
      title="Распознавание"
      icon="layers"
      bodyClassName="p-5 space-y-4"
      actions={pipeline.inFlight > 0 && <span className="flex items-center gap-1.5 text-xs text-sky-700"><Spinner /> идёт</span>}
    >
      {pipeline.isPending && <Loading />}
      {pipeline.error != null && <ErrorBox error={pipeline.error} />}
      {!pipeline.isPending && (
        <>
          <div>
            <div className="flex items-baseline justify-between text-sm">
              <span className="text-muted">Распознано</span>
              <span className="font-medium tabular-nums">
                {analyzed} из {pipeline.total}
              </span>
            </div>
            <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-ink/[0.07]">
              <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${share}%` }} />
            </div>
          </div>
          <ul className="space-y-1.5 text-sm">
            {PIPELINE.map((status) => (
              <li key={status} className="flex items-center gap-2.5">
                <Dot className={DOT[status]} />
                <span className="flex-1 text-muted">{label(ru.imageStatus, status)}</span>
                <span className="font-medium tabular-nums">{pipeline.value(status)}</span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted">
            После распознавания факты окон и выводы анализа обновляются сами. Непригодные кадры
            (темно, размыто, перекрыто) остаются в истории и помечаются.
          </p>
          <Button size="sm" icon="refresh" onClick={rerun} loading={reanalyze.isPending} disabled={pipeline.total === 0} className="w-full">
            Распознать заново
          </Button>
        </>
      )}
    </Panel>
  );
}

/** Снимки без времени съёмки: без него снимок не попадёт ни в одно окно наблюдения. */
export function NeedsTimePanel({ objectId }: { objectId: string }) {
  const images = useNeedsTime(objectId);
  const cameras = useQuery(camerasQuery(objectId));
  const code = new Map((cameras.data?.items ?? []).map((c) => [c.id, c.code]));
  const items = images.data?.items ?? [];
  if (images.isSuccess && items.length === 0) return null;
  return (
    <Panel
      title={`Снимки без времени: ${images.data?.total ?? "…"}`}
      description="Ни в EXIF, ни в имени файла времени не нашлось. Укажите его — снимок встанет в очередь распознавания."
      icon="clock"
      bodyClassName="divide-y divide-ink/[0.06]"
    >
      {images.isPending && <div className="px-5"><Loading /></div>}
      {images.isError && <div className="p-5"><ErrorBox error={images.error} /></div>}
      {items.map((image) => (
        <NeedsTimeRow key={image.id} image={image} camera={code.get(image.camera_id) ?? "…"} />
      ))}
      {(images.data?.total ?? 0) > items.length && (
        <p className="px-5 py-3 text-xs text-muted">Показаны первые {items.length}: после сохранения подгрузятся следующие.</p>
      )}
    </Panel>
  );
}

function NeedsTimeRow({ image, camera }: { image: ImageRead; camera: string }) {
  const detail = useQuery(imageQuery(image.id));
  const [local, setLocal] = useState("");
  const save = useSetImageTime();
  const toast = useToast();
  return (
    <div className="flex flex-wrap items-center gap-4 px-5 py-3">
      <a
        href={detail.data?.url}
        target="_blank"
        rel="noreferrer"
        className="h-14 w-24 shrink-0 overflow-hidden rounded-lg bg-ink/5 ring-1 ring-ink/[0.07]"
        title="Открыть снимок целиком"
      >
        {detail.data && <img src={detail.data.url} alt="" className="h-full w-full object-cover" />}
      </a>
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-medium">камера {camera}</p>
        <p className="text-xs text-muted">получен {formatMoment(image.received_at)}</p>
      </div>
      <input
        type="datetime-local"
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        className={fieldClass("input", "md", "w-auto")}
        aria-label="Время съёмки, московское"
      />
      <Button
        size="sm"
        variant="dark"
        icon="check"
        disabled={!local}
        loading={save.isPending}
        onClick={() =>
          save.mutate(
            { image, local },
            {
              onSuccess: () => toast.success("Время сохранено", "Снимок встал в очередь распознавания"),
              onError: (error) => toast.error(error, "Время не сохранено"),
            },
          )
        }
      >
        Сохранить
      </Button>
    </div>
  );
}

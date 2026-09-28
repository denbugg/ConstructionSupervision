import { useQuery } from "@tanstack/react-query";
import { useState, type DragEvent } from "react";
import { useParams } from "react-router-dom";

import { formatSize } from "@/entities/format";
import {
  entriesOf,
  fromDrop,
  fromInput,
  groupByCamera,
  guessParentFolder,
  totalBytes,
  type Picked,
} from "@/features/upload/files";
import { NeedsTimePanel, PipelinePanel } from "@/features/upload/UploadPanels";
import { useUploadImages, type CameraTarget, type IntakeResult } from "@/features/upload/useUpload";
import { camerasQuery } from "@/shared/api/queries";
import { Button } from "@/shared/ui/Button";
import { Field, inputClass, selectClass } from "@/shared/ui/Field";
import { Icon } from "@/shared/ui/Icon";
import { PageHeader, Panel } from "@/shared/ui/Page";
import { ErrorBox } from "@/shared/ui/QueryState";
import { useToast } from "@/shared/ui/Toast";

const FOLDERS = "__folders__";
const NEW_CAMERA = "__new__";

/**
 * Загрузка снимков (apps/web/README.md, §3): папка на камеру, прогресс, разбор итога,
 * очередь распознавания и ручное время для снимков, у которых его нет.
 */
export function UploadScreen() {
  const { objectId = "" } = useParams();
  const cameras = useQuery(camerasQuery(objectId));
  const upload = useUploadImages(objectId);
  const toast = useToast();
  const [picked, setPicked] = useState<Picked[]>([]);
  const [stripParent, setStripParent] = useState(false);
  const [cameraChoice, setCameraChoice] = useState(FOLDERS);
  const [newCode, setNewCode] = useState("");
  const [capturedAt, setCapturedAt] = useState("");
  const [dragging, setDragging] = useState(false);

  const take = (files: Picked[]) => {
    if (files.length === 0) {
      toast.info("Снимков не найдено", "Подходят изображения JPEG, PNG, WebP; скрытые файлы пропускаются.");
      return;
    }
    const hasFolders = files.some((f) => f.path.includes("/"));
    setPicked(files);
    setStripParent(guessParentFolder(files));
    setCameraChoice(hasFolders ? FOLDERS : (cameras.data?.items[0]?.code ?? NEW_CAMERA));
    upload.reset();
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    fromDrop(entriesOf(e.dataTransfer)).then(take, (error) => toast.error(error, "Не удалось прочитать файлы"));
  };

  const target: CameraTarget | null =
    cameraChoice === FOLDERS
      ? { kind: "folders", stripParent }
      : cameraChoice === NEW_CAMERA
        ? newCode.trim()
          ? { kind: "camera", code: newCode.trim() }
          : null
        : { kind: "camera", code: cameraChoice };
  const groups = cameraChoice === FOLDERS ? groupByCamera(picked, stripParent) : null;
  const orphans = groups?.get(null) ?? 0;

  const start = () => {
    if (!target) return;
    upload.mutate(
      { picked, target, capturedAt: capturedAt ? `${capturedAt}:00+03:00` : null },
      {
        onSuccess: (result) => {
          setPicked([]);
          if (result.rejected.length === 0) toast.success(`Принято снимков: ${result.accepted.length}`, "Распознавание уже идёт");
          else toast.info(`Принято ${result.accepted.length}, отклонено ${result.rejected.length}`, "Причины — в итоге загрузки");
        },
        onError: (error) => toast.error(error, "Снимки не загружены"),
      },
    );
  };

  return (
    <div>
      <PageHeader
        title="Загрузка снимков"
        description="Снимки камер → распознавание техники → факты для сверки с графиком. Время съёмки берётся из EXIF или имени файла."
      />
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-5">
          <Panel title="Новые снимки" icon="upload" bodyClassName="p-5 space-y-5">
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={`flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
                dragging ? "border-accent bg-accent/[0.05]" : "border-ink/15 bg-canvas/40"
              }`}
            >
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white text-accent shadow-sm ring-1 ring-ink/10">
                <Icon name="upload" size={22} />
              </span>
              <div>
                <p className="font-medium">Перетащите сюда снимки или папку</p>
                <p className="mt-1 text-sm text-muted">
                  Папка на камеру: <code className="rounded bg-ink/5 px-1">cam-north/20261020_090000.jpg</code> — камеры
                  заведутся сами
                </p>
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                <PickButton icon="image" label="Выбрать файлы" onPick={take} />
                <PickButton icon="folder" label="Выбрать папку" folder onPick={take} />
              </div>
            </div>

            {picked.length > 0 && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <p>
                    Выбрано <b>{picked.length}</b> снимков, {formatSize(totalBytes(picked))}
                  </p>
                  <Button size="sm" variant="ghost" icon="x" onClick={() => setPicked([])} disabled={upload.isPending}>
                    Очистить
                  </Button>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <Field label="Камера" hint={cameraChoice === FOLDERS ? "Первая папка в пути — код камеры" : "Все выбранные снимки — в эту камеру"}>
                    <select value={cameraChoice} onChange={(e) => setCameraChoice(e.target.value)} className={selectClass}>
                      <option value={FOLDERS}>По подпапкам (папка = камера)</option>
                      {(cameras.data?.items ?? []).map((c) => (
                        <option key={c.id} value={c.code}>
                          {c.name} ({c.code})
                        </option>
                      ))}
                      <option value={NEW_CAMERA}>Новая камера…</option>
                    </select>
                  </Field>
                  {cameraChoice === NEW_CAMERA ? (
                    <Field label="Код новой камеры" hint="Латиница, цифры, «-», «_», «.»" required>
                      <input value={newCode} onChange={(e) => setNewCode(e.target.value)} placeholder="cam-east" className={inputClass} />
                    </Field>
                  ) : (
                    <Field label="Время для снимков без времени" hint="Московское; если его нет ни в EXIF, ни в имени файла">
                      <input type="datetime-local" value={capturedAt} onChange={(e) => setCapturedAt(e.target.value)} className={inputClass} />
                    </Field>
                  )}
                </div>

                {groups && (
                  <div className="rounded-xl bg-canvas/60 p-3.5">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <p className="text-[13px] font-medium">Раскладка по камерам</p>
                      {picked.some((p) => p.path.split("/").length >= 3) && (
                        <label className="flex items-center gap-2 text-xs text-muted">
                          <input type="checkbox" checked={stripParent} onChange={(e) => setStripParent(e.target.checked)} />
                          выбранная папка — над папками камер
                        </label>
                      )}
                    </div>
                    <ul className="flex flex-wrap gap-2">
                      {[...groups].map(([camera, count]) => (
                        <li
                          key={camera ?? "none"}
                          className={`rounded-lg px-2.5 py-1 text-sm ring-1 ${camera ? "bg-white ring-ink/10" : "bg-red-50 text-red-800 ring-red-200"}`}
                        >
                          <span className="font-medium">{camera ?? "без папки"}</span> · {count}
                        </li>
                      ))}
                    </ul>
                    {orphans > 0 && (
                      <p className="mt-2 text-xs text-red-700">
                        Снимки без папки сервис отклонит: выберите камеру в списке выше или загрузите папку.
                      </p>
                    )}
                  </div>
                )}

                {upload.progress && <UploadProgressBar {...upload.progress} />}

                <div className="flex flex-wrap items-center gap-3">
                  <Button variant="primary" size="lg" icon="upload" loading={upload.isPending} disabled={!target} onClick={start}>
                    {upload.isPending ? "Загружаем…" : `Загрузить ${picked.length} снимков`}
                  </Button>
                  {!target && <span className="text-sm text-muted">Укажите код новой камеры</span>}
                </div>
              </div>
            )}
            {upload.isError && <ErrorBox error={upload.error} />}
          </Panel>

          {upload.data && <IntakeSummary result={upload.data} />}
          <NeedsTimePanel objectId={objectId} />
        </div>
        <PipelinePanel objectId={objectId} />
      </div>
    </div>
  );
}

function PickButton({
  icon,
  label,
  folder = false,
  onPick,
}: {
  icon: "image" | "folder";
  label: string;
  folder?: boolean;
  onPick: (files: Picked[]) => void;
}) {
  return (
    <label className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-lg bg-white px-3.5 text-sm font-medium shadow-sm ring-1 ring-inset ring-ink/15 hover:bg-stone-50">
      <Icon name={icon} size={16} />
      {label}
      <input
        type="file"
        multiple
        accept="image/*"
        className="sr-only"
        // Выбор папки — нестандартный атрибут: в типах React его нет, ставим напрямую.
        ref={(el) => {
          if (el && folder) el.setAttribute("webkitdirectory", "");
        }}
        onChange={(e) => {
          onPick(fromInput(e.target.files));
          e.target.value = "";
        }}
      />
    </label>
  );
}

function UploadProgressBar({ batch, batches, share }: { batch: number; batches: number; share: number }) {
  const overall = ((batch - 1 + share) / batches) * 100;
  return (
    <div className="space-y-1.5">
      <div className="h-2 overflow-hidden rounded-full bg-ink/[0.07]">
        <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${overall}%` }} />
      </div>
      <p className="text-xs text-muted">
        {share < 1 ? "Отправляем" : "Сервер сохраняет"} пакет {batch} из {batches} · {Math.round(overall)} %
      </p>
    </div>
  );
}

/** Итог загрузки: сколько принято, сколько ждёт времени, что отклонено и почему. */
function IntakeSummary({ result }: { result: IntakeResult }) {
  const needsTime = result.accepted.filter((a) => a.status === "NEEDS_TIME").length;
  const cameras = new Set(result.accepted.map((a) => a.camera_code));
  return (
    <Panel title="Итог загрузки" icon="check" bodyClassName="p-5 space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <SummaryFact label="Принято" value={result.accepted.length} hint={`камер: ${cameras.size}`} tone="text-emerald-700" />
        <SummaryFact label="Ждут времени" value={needsTime} hint="укажите ниже" tone={needsTime > 0 ? "text-amber-700" : ""} />
        <SummaryFact label="Отклонено" value={result.rejected.length} hint="причины ниже" tone={result.rejected.length > 0 ? "text-red-700" : ""} />
      </div>
      {result.rejected.length > 0 && (
        <div className="max-h-64 overflow-y-auto rounded-xl ring-1 ring-ink/10">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-stone-50 text-xs text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">Файл</th>
                <th className="px-3 py-2 font-medium">Почему отклонён</th>
              </tr>
            </thead>
            <tbody>
              {result.rejected.map((r, i) => (
                <tr key={`${r.file}-${i}`} className="border-t border-ink/[0.06]">
                  <td className="px-3 py-2 font-mono text-xs">{r.file}</td>
                  <td className="px-3 py-2">{r.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function SummaryFact({ label, value, hint, tone }: { label: string; value: number; hint: string; tone: string }) {
  return (
    <div className="rounded-xl bg-canvas/60 p-3">
      <p className="text-xs text-muted">{label}</p>
      <p className={`text-2xl font-semibold tabular-nums ${tone}`}>{value}</p>
      <p className="text-xs text-muted">{hint}</p>
    </div>
  );
}

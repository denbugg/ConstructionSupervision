/**
 * Подготовка файлов к загрузке: пути из выбора папки и перетаскивания, камера по подпапке,
 * деление на пакеты. site-service берёт камеру из первой папки в имени файла
 * (`cam-north/20261020_090000.jpg`), поэтому здесь решается, какая папка — камера.
 */

/** Файл и его путь относительно выбранного: `day1/cam-north/0900.jpg` или просто имя. */
export type Picked = { file: File; path: string };

// Ограничения одного запроса: 200 файлов у site-service, тело — с запасом до лимита gateway.
const BATCH_FILES = 200;
const BATCH_BYTES = 180 * 1024 * 1024;

const isImage = (file: File, path: string) =>
  file.type.startsWith("image/") && !path.split("/").some((part) => part.startsWith("."));

/** Из `<input type=file>`: у выбора папки браузер даёт `webkitRelativePath`. */
export function fromInput(files: FileList | null): Picked[] {
  return [...(files ?? [])]
    .map((file) => ({ file, path: file.webkitRelativePath || file.name }))
    .filter((p) => isImage(p.file, p.path));
}

/**
 * Из перетаскивания: папки обходятся рекурсивно. Записи берутся из `items` синхронно, в
 * обработчике события — после первого `await` браузер их уже не отдаст.
 */
export function entriesOf(transfer: DataTransfer): { entries: FileSystemEntry[]; files: File[] } {
  const entries = [...transfer.items]
    .map((item) => item.webkitGetAsEntry())
    .filter((entry): entry is FileSystemEntry => entry != null);
  return { entries, files: [...transfer.files] };
}

export async function fromDrop({ entries, files }: { entries: FileSystemEntry[]; files: File[] }): Promise<Picked[]> {
  if (entries.length === 0) return files.map((file) => ({ file, path: file.name })).filter((p) => isImage(p.file, p.path));
  const out: Picked[] = [];
  const walk = async (entry: FileSystemEntry, prefix: string): Promise<void> => {
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject));
      out.push({ file, path: `${prefix}${file.name}` });
      return;
    }
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    // readEntries отдаёт папку частями по ~100 записей: читаем, пока не вернёт пусто.
    for (;;) {
      const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
      if (batch.length === 0) break;
      for (const child of batch) await walk(child, `${prefix}${entry.name}/`);
    }
  };
  for (const entry of entries) await walk(entry, "");
  return out.filter((p) => isImage(p.file, p.path));
}

/**
 * Выбрана ли папка над папками камер. Если у всех файлов общая первая папка и все лежат
 * хотя бы на уровень глубже, первая папка — это выбранный «день», а камеры — внутри.
 */
export function guessParentFolder(picked: Picked[]): boolean {
  if (picked.length === 0) return false;
  const parts = picked.map((p) => p.path.split("/"));
  const first = parts[0]?.[0];
  return parts.every((segments) => segments.length >= 3 && segments[0] === first);
}

/** Путь, который уйдёт в имени файла: без выбранной родительской папки. */
export function uploadName(picked: Picked, stripParent: boolean): string {
  if (!stripParent) return picked.path;
  return picked.path.split("/").slice(1).join("/");
}

/** Камера файла по первой папке пути; `null` — файл лежит без папки. */
export function cameraOf(name: string): string | null {
  const parts = name.split("/");
  return parts.length >= 2 ? (parts[0] ?? null) : null;
}

/** Сколько файлов уйдёт в каждую камеру — превью перед загрузкой. */
export function groupByCamera(picked: Picked[], stripParent: boolean): Map<string | null, number> {
  const groups = new Map<string | null, number>();
  for (const p of picked) {
    const camera = cameraOf(uploadName(p, stripParent));
    groups.set(camera, (groups.get(camera) ?? 0) + 1);
  }
  return groups;
}

/** Пакеты для отправки: не больше 200 файлов и ~180 МБ в одном запросе. */
export function batches(picked: Picked[]): Picked[][] {
  const out: Picked[][] = [];
  let current: Picked[] = [];
  let bytes = 0;
  for (const p of picked) {
    if (current.length > 0 && (current.length >= BATCH_FILES || bytes + p.file.size > BATCH_BYTES)) {
      out.push(current);
      current = [];
      bytes = 0;
    }
    current.push(p);
    bytes += p.file.size;
  }
  if (current.length > 0) out.push(current);
  return out;
}

export function totalBytes(picked: Picked[]): number {
  return picked.reduce((sum, p) => sum + p.file.size, 0);
}

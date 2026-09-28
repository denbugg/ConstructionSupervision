import type { CameraRead } from "@/shared/api/queries";
import { Icon } from "@/shared/ui/Icon";

/** Переключатель камер объекта; выключенная камера видна, но помечена. */
export function CameraTabs({
  cameras,
  current,
  onSelect,
}: {
  cameras: CameraRead[];
  current: CameraRead;
  onSelect: (camera: CameraRead) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2" role="tablist" aria-label="Камеры">
      {cameras.map((camera) => {
        const active = camera.id === current.id;
        return (
          <button
            key={camera.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onSelect(camera)}
            title={camera.code}
            className={`inline-flex h-9 items-center gap-2 rounded-lg px-3 text-sm font-medium shadow-sm ring-1 transition-colors ${
              active ? "bg-ink text-white ring-ink" : "bg-white text-ink ring-ink/15 hover:ring-ink/30"
            } ${camera.is_active ? "" : "opacity-60"}`}
          >
            <Icon name="camera" size={15} className={active ? "text-white/70" : "text-muted"} />
            {camera.name}
            {!camera.is_active && <span className="text-xs font-normal">выключена</span>}
          </button>
        );
      })}
    </div>
  );
}

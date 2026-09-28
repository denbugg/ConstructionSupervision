import type { Point } from "@/entities/polygon";
import { centroid } from "@/entities/polygon";

/**
 * Фигуры поверх кадра (`Frame`). Координаты приходят в долях 0…1, как в API, и здесь же
 * переводятся в пиксели viewBox. Размер подписей — доля ширины кадра, чтобы подпись читалась
 * одинаково на 1280 и на 3840 пикселях.
 */

type Size = { width: number; height: number };

const toPixels = (points: Point[], { width, height }: Size) =>
  points.map(([x, y]) => `${x * width},${y * height}`).join(" ");

export const fontSize = ({ width }: Size) => Math.max(12, width * 0.013);

export function Label({
  at,
  text,
  color,
  size,
}: {
  at: [number, number];
  text: string;
  color: string;
  size: Size;
}) {
  const fs = fontSize(size);
  // Ширина плашки по числу символов: SVG не меряет текст до отрисовки, а точность тут не нужна.
  const w = text.length * fs * 0.58 + fs * 0.6;
  return (
    <g pointerEvents="none">
      <rect x={at[0]} y={at[1] - fs * 1.25} width={w} height={fs * 1.4} rx={fs * 0.2} fill={color} />
      <text x={at[0] + fs * 0.3} y={at[1] - fs * 0.2} fontSize={fs} fill="white">
        {text}
      </text>
    </g>
  );
}

export function ZoneOutline({
  polygon,
  color,
  label,
  size,
  muted = false,
}: {
  polygon: Point[];
  color: string;
  label: string;
  size: Size;
  muted?: boolean;
}) {
  const [cx, cy] = centroid(polygon);
  return (
    <g opacity={muted ? 0.45 : 1}>
      <polygon
        points={toPixels(polygon, size)}
        fill={color}
        fillOpacity={0.15}
        stroke={color}
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
        pointerEvents="none"
      />
      <Label at={[cx * size.width, cy * size.height]} text={label} color={color} size={size} />
    </g>
  );
}

/** Рамка детекции и точка контакта с землёй: по этой точке site выбрал зону машины. */
export function DetectionBox({
  bbox,
  anchor,
  label,
  color,
  size,
}: {
  bbox: number[];
  anchor: number[];
  label: string;
  color: string;
  size: Size;
}) {
  // В API рамка и точка — массивы чисел без длины в типе; нули не нарисуются заметно.
  const [x1 = 0, y1 = 0, x2 = 0, y2 = 0] = bbox;
  const [ax = 0, ay = 0] = anchor;
  const { width: w, height: h } = size;
  return (
    <g>
      <rect
        x={x1 * w}
        y={y1 * h}
        width={(x2 - x1) * w}
        height={(y2 - y1) * h}
        fill="none"
        stroke={color}
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
      />
      <circle cx={ax * w} cy={ay * h} r={w * 0.004} fill={color} />
      <Label at={[x1 * w, y1 * h]} text={label} color={color} size={size} />
    </g>
  );
}

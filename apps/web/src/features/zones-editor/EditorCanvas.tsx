import { useRef, useState, type PointerEvent } from "react";

import { midpoints, type Point } from "@/entities/polygon";
import { zoneColor } from "@/entities/zones";
import type { Action, DraftZone } from "@/features/zones-editor/draft";
import { Frame, pointerToFrame } from "@/shared/ui/Frame";
import { Label, ZoneOutline } from "@/shared/ui/overlays";

type Size = { width: number; height: number };

type Drag =
  | { kind: "vertex"; key: string; index: number }
  | { kind: "move"; key: string; start: Point; from: Point[] };

/** Щелчок ближе этой доли ширины кадра к первой точке замыкает новый полигон. */
const CLOSE_DISTANCE = 0.015;

/**
 * Кадр с зонами камеры. Выбранная зона редактируется: вершины тянутся, «+» на середине ребра
 * добавляет вершину, двойной щелчок по вершине её удаляет, тело зоны двигает её целиком.
 * В режиме рисования щелчки ставят вершины новой зоны; замыкает щелчок по первой точке.
 */
export function EditorCanvas({
  url,
  size,
  zones,
  selected,
  drawing,
  anchors,
  onDraw,
  dispatch,
}: {
  url: string;
  size: Size;
  zones: DraftZone[];
  selected: string | null;
  drawing: Point[] | null;
  /** Где стояла техника на снимках камеры: точка и цвет её класса. */
  anchors: { id: string; point: Point; color: string }[];
  onDraw: (points: Point[] | null, finished?: boolean) => void;
  dispatch: (action: Action) => void;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [cursor, setCursor] = useState<Point | null>(null);
  const r = size.width * 0.006;

  const at = (e: PointerEvent): Point => pointerToFrame(svg.current!, e.clientX, e.clientY);

  const startDrag = (e: PointerEvent, next: Drag) => {
    e.stopPropagation();
    svg.current?.setPointerCapture(e.pointerId);
    setDrag(next);
  };

  const onPointerMove = (e: PointerEvent) => {
    const p = at(e);
    if (drawing) setCursor(p);
    if (!drag) return;
    if (drag.kind === "vertex") {
      dispatch({ type: "moveVertex", key: drag.key, index: drag.index, to: p });
    } else {
      const [dx, dy] = [p[0] - drag.start[0], p[1] - drag.start[1]];
      dispatch({ type: "translate", key: drag.key, from: drag.from, dx, dy });
    }
  };

  const onBackgroundDown = (e: PointerEvent) => {
    if (!drawing) {
      dispatch({ type: "select", key: null });
      return;
    }
    const p = at(e);
    const first = drawing[0];
    // Расстояние — в долях ширины по обеим осям: доля высоты у широкого кадра короче.
    const closes =
      first !== undefined &&
      drawing.length >= 3 &&
      Math.hypot(p[0] - first[0], (p[1] - first[1]) * (size.height / size.width)) < CLOSE_DISTANCE;
    onDraw(closes ? drawing : [...drawing, p], closes);
  };

  const visible = zones.filter((z) => !z.deleted);
  const current = visible.find((z) => z.key === selected);

  return (
    <Frame
      ref={svg}
      url={url}
      alt="Эталонный кадр камеры"
      {...size}
      svgProps={{
        onPointerMove,
        onPointerUp: () => setDrag(null),
        onPointerLeave: () => setCursor(null),
        style: { cursor: drawing ? "crosshair" : "default", touchAction: "none" },
      }}
    >
      <rect width={size.width} height={size.height} fill="transparent" onPointerDown={onBackgroundDown} />
      <g pointerEvents="none">
        {anchors.map((a) => (
          <circle
            key={a.id}
            cx={a.point[0] * size.width}
            cy={a.point[1] * size.height}
            r={r}
            fill={a.color}
            fillOpacity={0.85}
            stroke="white"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </g>
      {visible.map((zone) => (
        <g
          key={zone.key}
          onPointerDown={(e) => {
            if (drawing) return;
            dispatch({ type: "select", key: zone.key });
            startDrag(e, { kind: "move", key: zone.key, start: at(e), from: zone.polygon });
          }}
          style={{ cursor: drawing ? "crosshair" : "move" }}
          pointerEvents={drawing ? "none" : "all"}
        >
          <polygon
            points={zone.polygon.map(([x, y]) => `${x * size.width},${y * size.height}`).join(" ")}
            fill="transparent"
          />
          <ZoneOutline
            polygon={zone.polygon}
            color={zoneColor(zone.zoneType)}
            label={zone.name || "без названия"}
            size={size}
            muted={current != null && current.key !== zone.key}
          />
        </g>
      ))}
      {current && !drawing && (
        <g>
          {midpoints(current.polygon).map(([x, y], i) => (
            <g
              key={`mid-${i}`}
              style={{ cursor: "copy" }}
              onPointerDown={(e) => {
                dispatch({ type: "insertVertex", key: current.key, after: i, at: [x, y] });
                startDrag(e, { kind: "vertex", key: current.key, index: i + 1 });
              }}
            >
              <circle cx={x * size.width} cy={y * size.height} r={r * 0.8} fill="white" stroke="#15181a" strokeWidth={1} vectorEffect="non-scaling-stroke" />
              <text x={x * size.width} y={y * size.height + r * 0.45} fontSize={r * 1.4} textAnchor="middle" pointerEvents="none">
                +
              </text>
            </g>
          ))}
          {current.polygon.map(([x, y], i) => (
            <circle
              key={`v-${i}`}
              cx={x * size.width}
              cy={y * size.height}
              r={r}
              fill={zoneColor(current.zoneType)}
              stroke="white"
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
              style={{ cursor: "grab" }}
              onPointerDown={(e) => startDrag(e, { kind: "vertex", key: current.key, index: i })}
              onDoubleClick={() => dispatch({ type: "removeVertex", key: current.key, index: i })}
            />
          ))}
        </g>
      )}
      {drawing && <DrawingPreview points={drawing} cursor={cursor} size={size} r={r} />}
    </Frame>
  );
}

function DrawingPreview({
  points,
  cursor,
  size,
  r,
}: {
  points: Point[];
  cursor: Point | null;
  size: Size;
  r: number;
}) {
  const path = [...points, ...(cursor ? [cursor] : [])]
    .map(([x, y]) => `${x * size.width},${y * size.height}`)
    .join(" ");
  const first = points[0];
  return (
    <g pointerEvents="none">
      <polyline points={path} fill="none" stroke="#c2451a" strokeWidth={2} strokeDasharray="6 4" vectorEffect="non-scaling-stroke" />
      {points.map(([x, y], i) => (
        <circle key={i} cx={x * size.width} cy={y * size.height} r={i === 0 ? r * 1.3 : r * 0.8} fill="#c2451a" stroke="white" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      ))}
      {first && (
        <Label
          at={[first[0] * size.width + r * 1.6, first[1] * size.height - r]}
          text={points.length >= 3 ? "щёлкните сюда, чтобы замкнуть" : `точек: ${points.length}`}
          color="#c2451a"
          size={size}
        />
      )}
    </g>
  );
}

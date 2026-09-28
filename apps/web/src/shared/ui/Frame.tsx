import { forwardRef, type ReactNode, type SVGProps } from "react";

import type { Point } from "@/entities/polygon";

type FrameProps = {
  url: string;
  alt: string;
  /** Размер кадра в пикселях: в нём задан viewBox слоя. */
  width: number;
  height: number;
  children?: ReactNode;
  svgProps?: SVGProps<SVGSVGElement>;
};

/**
 * Снимок и SVG-слой поверх него (apps/web/README.md, §3). viewBox — в пикселях кадра, а не
 * 0…1: при растягивании 0…1 на неквадратный кадр круги вершин стали бы эллипсами. Толщина
 * линий задаётся `vector-effect: non-scaling-stroke` у самих фигур.
 */
export const Frame = forwardRef<SVGSVGElement, FrameProps>(function Frame(
  { url, alt, width, height, children, svgProps },
  ref,
) {
  return (
    <div className="relative select-none overflow-hidden rounded-lg bg-ink/5">
      <img src={url} alt={alt} className="block w-full" draggable={false} />
      <svg
        ref={ref}
        viewBox={`0 0 ${width} ${height}`}
        className="absolute inset-0 h-full w-full"
        {...svgProps}
      >
        {children}
      </svg>
    </div>
  );
});

/** Точка курсора в долях кадра 0…1 — в тех же единицах, что полигоны и рамки API. */
export function pointerToFrame(svg: SVGSVGElement, clientX: number, clientY: number): Point {
  const box = svg.getBoundingClientRect();
  return [(clientX - box.left) / box.width, (clientY - box.top) / box.height];
}

/**
 * Геометрия полигона зоны в долях кадра 0…1 (ADR-0006). Чистые функции: редактор хранит
 * полигон как массив точек и меняет его только через них, поэтому точка за краем кадра или
 * полигон из двух вершин получиться не могут.
 */

export type Point = [number, number];

/** Меньше трёх вершин полигон не сохраняет и сам site-service (`INVALID_POLYGON`). */
export const MIN_VERTICES = 3;

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/** Четыре знака после запятой — десятая доля пикселя 4K-кадра; больше — шум в файле. */
const round = (v: number) => Math.round(v * 10000) / 10000;

export function clampPoint([x, y]: Point): Point {
  return [round(clamp01(x)), round(clamp01(y))];
}

export function moveVertex(polygon: Point[], index: number, to: Point): Point[] {
  return polygon.map((p, i) => (i === index ? clampPoint(to) : p));
}

/** Новая вершина после `index` — на ребре к следующей вершине. */
export function insertVertex(polygon: Point[], index: number, at: Point): Point[] {
  return [...polygon.slice(0, index + 1), clampPoint(at), ...polygon.slice(index + 1)];
}

/** Удаление вершины; до трёх вершин полигон не сокращается. */
export function removeVertex(polygon: Point[], index: number): Point[] {
  if (polygon.length <= MIN_VERTICES) return polygon;
  return polygon.filter((_, i) => i !== index);
}

/**
 * Сдвиг всего полигона. Сдвиг урезается так, чтобы ни одна вершина не ушла за край: иначе
 * полигон у края сплющился бы, а не упёрся.
 */
export function translate(polygon: Point[], dx: number, dy: number): Point[] {
  const xs = polygon.map((p) => p[0]);
  const ys = polygon.map((p) => p[1]);
  const sx = Math.min(Math.max(dx, -Math.min(...xs)), 1 - Math.max(...xs));
  const sy = Math.min(Math.max(dy, -Math.min(...ys)), 1 - Math.max(...ys));
  return polygon.map(([x, y]) => clampPoint([x + sx, y + sy]));
}

/** Середины рёбер: за них тянут, чтобы добавить вершину. */
export function midpoints(polygon: Point[]): Point[] {
  return polygon.map((p, i) => {
    const q = vertex(polygon, i + 1);
    return [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
  });
}

/** Вершина по индексу с переходом через конец: у полигона за последней идёт первая. */
function vertex(polygon: Point[], index: number): Point {
  return polygon[index % polygon.length] ?? [0, 0];
}

export function centroid(polygon: Point[]): Point {
  const n = polygon.length || 1;
  return [polygon.reduce((s, p) => s + p[0], 0) / n, polygon.reduce((s, p) => s + p[1], 0) / n];
}

function cross(o: Point, a: Point, b: Point): number {
  return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
}

function segmentsCross(a: Point, b: Point, c: Point, d: Point): boolean {
  const d1 = cross(c, d, a);
  const d2 = cross(c, d, b);
  const d3 = cross(a, b, c);
  const d4 = cross(a, b, d);
  return d1 * d2 < 0 && d3 * d4 < 0;
}

/**
 * Самопересечение — «восьмёрка»: такую зону site-service не примет. Проверка нужна, чтобы
 * сказать об этом до сохранения, а не ошибкой после. Соседние рёбра не сравниваются.
 */
export function selfIntersects(polygon: Point[]): boolean {
  const n = polygon.length;
  for (let i = 0; i < n; i++) {
    for (let j = i + 2; j < n; j++) {
      if (i === 0 && j === n - 1) continue;
      const [a, b] = [vertex(polygon, i), vertex(polygon, i + 1)];
      if (segmentsCross(a, b, vertex(polygon, j), vertex(polygon, j + 1))) {
        return true;
      }
    }
  }
  return false;
}

/** Полигоны равны до округления: так редактор понимает, есть ли несохранённая правка. */
export function samePolygon(a: Point[], b: Point[]): boolean {
  return (
    a.length === b.length &&
    a.every((p, i) => {
      const q = b[i];
      return q !== undefined && p[0] === q[0] && p[1] === q[1];
    })
  );
}

/**
 * Иконки интерфейса: контурные, 24×24, цвет — `currentColor`. Свой набор из тридцати путей
 * вместо библиотеки: зависимость ради них не окупается (AGENTS.md, §6).
 */

const PATHS = {
  plus: "M12 5v14M5 12h14",
  check: "M5 12.5l4.5 4.5L19 7.5",
  x: "M6 6l12 12M18 6L6 18",
  chevronDown: "M6 9l6 6 6-6",
  chevronRight: "M9 6l6 6-6 6",
  chevronLeft: "M15 6l-6 6 6 6",
  arrowRight: "M5 12h14M13 6l6 6-6 6",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4",
  home: "M4 11l8-7 8 7M6 9.5V20h12V9.5M10 20v-5h4v5",
  alert: "M12 4L2.5 20h19L12 4zM12 10v4M12 17h.01",
  gantt: "M3 3v18h18M7 7h7M10 12h9M7 17h6",
  camera: "M4 8h3l2-3h6l2 3h3v11H4zM12 16a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  image: "M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M15 9h.01",
  upload: "M12 15V4M7 9l5-5 5 5M4 15v5h16v-5",
  download: "M12 4v11M7 10l5 5 5-5M4 20h16",
  report: "M7 3h8l4 4v14H7zM15 3v4h4M10 12h6M10 16h6",
  sliders: "M4 7h9M17 7h3M4 17h3M11 17h9M15 5v4M9 15v4",
  rules: "M4 6l1.5 1.5L8 5M4 12l1.5 1.5L8 11M4 18l1.5 1.5L8 17M11 6h9M11 12h9M11 18h9",
  zones: "M12 3l8.5 6.2-3.2 10.3H6.7L3.5 9.2z",
  gauge: "M4 17a8 8 0 1 1 16 0M12 17l4-5",
  truck: "M2 7h11v9H2zM13 10h4l3 3v3h-7M6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM17 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  building: "M4 21V6l8-3v18M12 9h8v12M3 21h18M8 8v.01M8 12v.01M8 16v.01M16 13v.01M16 17v.01",
  edit: "M4 20h4L19 9l-4-4L4 16v4zM13.5 6.5l4 4",
  archive: "M3 4h18v4H3zM5 8v12h14V8M10 12h4",
  restore: "M4 12a8 8 0 1 0 2.3-5.7M4 4v5h5",
  trash: "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13",
  refresh: "M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5",
  play: "M7 5v14l12-7z",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
  calendar: "M4 6h16v14H4zM4 10h16M8 4v4M16 4v4",
  folder: "M3 6h6l2 2h10v11H3z",
  external: "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v5M12 8h.01",
  menu: "M4 7h16M4 12h16M4 17h16",
  eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  layers: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5",
  power: "M12 3v9M6.3 6.3a8 8 0 1 0 11.4 0",
  filter: "M4 5h16l-6 7v6l-4 2v-8z",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  sparkle: "M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M18 6l-2.5 2.5M8.5 15.5L6 18",
} as const;

export type IconName = keyof typeof PATHS;

// Точки «ещё» — отрезки нулевой длины: видны только при толстой линии.
const STROKE: Partial<Record<IconName, number>> = { more: 3 };

export function Icon({
  name,
  size = 16,
  className = "",
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={STROKE[name] ?? 1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 ${className}`}
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

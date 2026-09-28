/// <reference types="vite/client" />

/** Переменные сборки, которые читает интерфейс. Все — с префиксом VITE_. */
interface ImportMetaEnv {
  readonly VITE_API_KEY?: string;
  readonly VITE_API_PROXY?: string;
  readonly VITE_ACTOR?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/**
 * Обёртка над HTTP-вызовами к API.
 *
 * Единственное место, где интерфейс знает про конверт ошибки
 * `{"error": {code, message, details, request_id}}` и про ключ доступа.
 * Типы ответов — из `packages/ts-api-client` (`shared/api/schemas.ts`);
 * дублировать их руками нельзя.
 */

/** Ошибка API в том виде, в каком её показывают пользователю. */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly requestId: string | null,
    readonly status: number,
    /** `details` конверта: например, построчные ошибки импорта графика. */
    readonly details: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Путь относительный: в проде статику и API отдаёт один gateway, в разработке
// запрос проксирует Vite. Абсолютный адрес сервиса в коде — ошибка.
const API_BASE = "/api/v1";
const API_KEY = import.meta.env.VITE_API_KEY ?? "dev-key-change-me";
// Кто правит — для журналов сервисов (вердикт, правка правила). Ролей нет (ADR-0010),
// поэтому это одно имя на интерфейс. В заголовке — URL-кодировка: кириллица не ASCII.
const ACTOR = encodeURIComponent(import.meta.env.VITE_ACTOR ?? "оператор");

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "X-API-Key": API_KEY },
    signal,
  });

  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as T;
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return sendJson<T>("POST", path, body);
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return sendJson<T>("PATCH", path, body);
}

/** Удаление: сервисы отвечают `204` без тела, поэтому результата нет. */
export async function apiDelete(path: string): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
    headers: { "X-API-Key": API_KEY, "X-Actor": ACTOR },
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
}

/** Файлы — `multipart/form-data`; заголовок с границей частей ставит сам браузер. */
export async function apiPostForm<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "X-API-Key": API_KEY, "X-Actor": ACTOR },
    body: form,
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as T;
}

/**
 * Отправка файлов с прогрессом. У fetch нет событий отправки тела, поэтому здесь
 * XMLHttpRequest; `onProgress` получает долю отправленных байт 0…1.
 */
export function apiUpload<T>(
  path: string,
  form: FormData,
  onProgress: (share: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}${path}`);
    xhr.setRequestHeader("X-API-Key", API_KEY);
    xhr.setRequestHeader("X-Actor", ACTOR);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as T);
        return;
      }
      toApiError(new Response(xhr.responseText, { status: xhr.status })).then(reject, reject);
    };
    xhr.onerror = () =>
      reject(new ApiError("NETWORK_ERROR", "Сервер недоступен: файлы не отправлены", null, 0));
    xhr.send(form);
  });
}

async function sendJson<T>(method: "POST" | "PATCH", path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { "X-API-Key": API_KEY, "X-Actor": ACTOR, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as T;
}

async function toApiError(response: Response): Promise<ApiError> {
  // Ответ мог прийти не от сервиса, а от gateway или прокси — тогда это
  // не наш конверт, и придумывать код ошибки за него мы не станем.
  try {
    const payload = (await response.json()) as {
      error?: { code?: string; message?: string; request_id?: string; details?: unknown };
    };
    const error = payload.error;
    if (error?.message) {
      return new ApiError(
        error.code ?? "UNKNOWN",
        error.message,
        error.request_id ?? null,
        response.status,
        error.details ?? null,
      );
    }
  } catch {
    // тело не JSON — ниже вернём ошибку по коду ответа
  }
  return new ApiError("HTTP_ERROR", `HTTP ${response.status}`, null, response.status);
}

// В деплое backend живёт на Render (отдельный домен, берём из
// VITE_API_BASE_URL). Локально (Vite dev server) переменная не задана,
// и запросы идут на тот же origin через прокси из vite.config.ts.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

// Общий секрет, отсекающий ботов/скан(н)еры, дёргающие публичный URL
// Render напрямую, минуя сайт (см. backend/app/core/shared_secret.py).
// Это НЕ настоящая аутентификация — значение попадает в клиентский бандл
// и видно в devtools любому, кто открыл легитимный сайт. Если переменная
// не задана, заголовок просто не добавляется — backend тогда тоже не
// требует его (no-op), так что это безопасно для локальной разработки.
const APP_SHARED_SECRET = import.meta.env.VITE_APP_SHARED_SECRET ?? "";
const SHARED_SECRET_HEADER = "X-App-Secret";

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export async function parseErrorOrJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? "Запрос не удался");
  }
  return res.json();
}

// Render Free "засыпает" после ~15 минут без запросов и может просыпаться
// секунды-десятки секунд на первый запрос — за это время fetch падает с
// сетевой ошибкой ("Failed to fetch") или прокси перед сервисом отдаёт
// 502/503/504. fetchWithWakeup автоматически повторяет запрос с нарастающей
// паузой (суммарно ~70 секунд), сообщая через onWaking(true/false), что
// сейчас происходит — страница может показать «Сервер просыпается…».
//
// FormData/File можно безопасно передавать в fetch() повторно (это не
// одноразовый поток), поэтому один и тот же RequestInit годится для всех
// попыток, включая загрузку файлов.
const WAKEUP_RETRY_DELAYS_MS = [2000, 3000, 5000, 5000, 8000, 8000, 10000, 10000, 10000, 10000];

function isGatewayStatus(status: number): boolean {
  return status === 502 || status === 503 || status === 504;
}

export async function fetchWithWakeup(
  input: string,
  init?: RequestInit,
  onWaking?: (waking: boolean) => void
): Promise<Response> {
  // Общий для всех модулей fetch-хелпер — добавляя заголовок здесь, а не
  // в каждом api/*.ts, покрываем все вызовы автоматически.
  const headers = new Headers(init?.headers);
  if (APP_SHARED_SECRET) headers.set(SHARED_SECRET_HEADER, APP_SHARED_SECRET);
  const initWithSecret: RequestInit = { ...init, headers };

  let sawFailure = false;
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(input, initWithSecret);
      if (isGatewayStatus(res.status) && attempt < WAKEUP_RETRY_DELAYS_MS.length) {
        throw new Error(`gateway ${res.status}`);
      }
      if (sawFailure) onWaking?.(false);
      return res;
    } catch (e) {
      if ((e as Error).name === "AbortError" || attempt >= WAKEUP_RETRY_DELAYS_MS.length) {
        if (sawFailure) onWaking?.(false);
        throw e;
      }
      sawFailure = true;
      onWaking?.(true);
      await new Promise((r) => setTimeout(r, WAKEUP_RETRY_DELAYS_MS[attempt]));
    }
  }
}

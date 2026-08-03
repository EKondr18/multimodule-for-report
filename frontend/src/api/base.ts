// В деплое backend живёт на Render (отдельный домен, берём из
// VITE_API_BASE_URL). Локально (Vite dev server) переменная не задана,
// и запросы идут на тот же origin через прокси из vite.config.ts.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

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
  let sawFailure = false;
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(input, init);
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

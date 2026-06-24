// В деплое на Vercel backend живёт на отдельном домене — берём его из
// VITE_API_BASE_URL. Локально (Vite dev server) переменная не задана,
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

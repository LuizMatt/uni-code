const TOKEN_KEY = "unicode_admin_token";

export function getStoredToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers = new Headers(options.headers || {});

  if (token) {
    headers.set("Authorization", `Basic ${token}`);
  }

  const response = await fetch(path, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    clearStoredToken();
    window.location.href = "/login";
    throw new Error("Não autenticado.");
  }

  if (!response.ok) {
    let errorDetail = `Erro HTTP ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson?.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return response.json() as Promise<T>;
}

export async function downloadGradesCsv(unitCode: string, classGroup?: string): Promise<void> {
  const token = getStoredToken();
  const headers = new Headers();
  if (token) {
    headers.set("Authorization", `Basic ${token}`);
  }

  let url = `/api/export.csv?unit=${encodeURIComponent(unitCode)}`;
  if (classGroup) {
    url += `&class_group=${encodeURIComponent(classGroup)}`;
  }

  const response = await fetch(url, { headers });
  if (response.status === 401) {
    clearStoredToken();
    window.location.href = "/login";
    throw new Error("Não autenticado.");
  }
  if (!response.ok) {
    throw new Error("Falha ao exportar CSV.");
  }

  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = downloadUrl;
  a.download = `notas-${unitCode}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(downloadUrl);
}


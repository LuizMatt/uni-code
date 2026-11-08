import {
  ImportCsvReport,
  StudentCreateInput,
  StudentMutationResponse,
  StudentUpdateInput,
} from "./types";

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

export async function createStudent(
  payload: StudentCreateInput
): Promise<StudentMutationResponse> {
  return apiFetch<StudentMutationResponse>("/api/students", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateStudent(
  registration: string,
  payload: StudentUpdateInput
): Promise<StudentMutationResponse> {
  return apiFetch<StudentMutationResponse>(
    `/api/students/${encodeURIComponent(registration)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export async function deleteStudent(
  registration: string
): Promise<{ deleted: boolean; registration: string }> {
  return apiFetch<{ deleted: boolean; registration: string }>(
    `/api/students/${encodeURIComponent(registration)}`,
    {
      method: "DELETE",
    }
  );
}

export async function deleteClassGroup(
  classGroup: string
): Promise<{ deleted: boolean; class_group: string; count: number }> {
  return apiFetch<{ deleted: boolean; class_group: string; count: number }>(
    `/api/students/classes/${encodeURIComponent(classGroup)}`,
    {
      method: "DELETE",
    }
  );
}

export async function uploadStudentsCsv(file: File): Promise<ImportCsvReport> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch<ImportCsvReport>("/api/students/import-csv", {
    method: "POST",
    body: formData,
  });
}

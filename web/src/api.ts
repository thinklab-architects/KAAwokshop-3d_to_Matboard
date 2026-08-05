import type { Project } from "./types";

const API = "/api";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* keep the status line */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const listProjects = () => fetch(`${API}/projects`).then(json<Project[]>);

export const deleteProject = (id: string) =>
  fetch(`${API}/projects/${id}`, { method: "DELETE" }).then(json<{ deleted: string }>);

export const health = () =>
  fetch(`${API}/health`).then(json<{ ok: boolean; sdk: string; sketchup: string }>);

export function uploadProject(file: File, onProgress?: (pct: number) => void): Promise<Project> {
  // XHR rather than fetch, because upload progress is the whole point here:
  // a 200 MB .skp over a slow link needs a bar, not a spinner.
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API}/projects`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as Project);
      } else {
        let msg = `${xhr.status} ${xhr.statusText}`;
        try {
          msg = JSON.parse(xhr.responseText).detail ?? msg;
        } catch {
          /* keep the status line */
        }
        reject(new Error(msg));
      }
    };
    xhr.onerror = () => reject(new Error("上傳失敗：無法連線到伺服器"));
    xhr.send(form);
  });
}

export const projectBase = (id: string) => `${API}/projects/${id}`;

import type { Box, Dataset, ImageRecord, TrainingRun } from "./types";

const BASE = "/api";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch(`${BASE}/health`).then((r) => j<{ status: string }>(r)),

  // datasets
  listDatasets: () => fetch(`${BASE}/datasets`).then((r) => j<Dataset[]>(r)),
  getDataset: (id: number) =>
    fetch(`${BASE}/datasets/${id}`).then((r) => j<Dataset>(r)),
  createDataset: (name: string, class_names: string[]) =>
    fetch(`${BASE}/datasets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, class_names }),
    }).then((r) => j<Dataset>(r)),
  deleteDataset: async (id: number) => {
    const res = await fetch(`${BASE}/datasets/${id}`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) {
      const text = await res.text();
      throw new Error(text || `${res.status} ${res.statusText}`);
    }
  },

  // images
  upload: async (datasetId: number, files: FileList | File[]) => {
    const fd = new FormData();
    for (const f of Array.from(files)) fd.append("files", f);
    const res = await fetch(`${BASE}/datasets/${datasetId}/upload`, {
      method: "POST",
      body: fd,
    });
    return j<ImageRecord[]>(res);
  },
  listImages: (datasetId: number, status?: string) => {
    const q = status ? `?status=${encodeURIComponent(status)}` : "";
    return fetch(`${BASE}/datasets/${datasetId}/images${q}`).then((r) => j<ImageRecord[]>(r));
  },
  getImage: (id: number) =>
    fetch(`${BASE}/images/${id}`).then((r) => j<ImageRecord>(r)),
  imageUrl: (id: number) => `${BASE}/images/${id}/file`,

  // labels
  updateLabels: (
    imageId: number,
    boxes: Omit<Box, "id">[],
    status: "labeled" | "reviewed" | "rejected" = "labeled"
  ) =>
    fetch(`${BASE}/images/${imageId}/labels`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ boxes, status }),
    }).then((r) => j<ImageRecord>(r)),

  // training
  startTrain: (datasetId: number, epochs = 20, img_size = 640) =>
    fetch(`${BASE}/datasets/${datasetId}/train`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ epochs, img_size }),
    }).then((r) => j<TrainingRun>(r)),
  listRuns: (datasetId: number) =>
    fetch(`${BASE}/datasets/${datasetId}/runs`).then((r) => j<TrainingRun[]>(r)),

  // predict
  predictUnlabeled: (datasetId: number, conf_threshold = 0.25) =>
    fetch(`${BASE}/datasets/${datasetId}/predict`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conf_threshold }),
    }).then((r) => j<{ queued: number; weights: string }>(r)),

  // review queue
  queue: (datasetId: number, limit = 50, sort = "confidence_asc") =>
    fetch(
      `${BASE}/datasets/${datasetId}/queue?limit=${limit}&sort=${sort}`
    ).then((r) => j<ImageRecord[]>(r)),

  exportYoloUrl: (datasetId: number) =>
    `${BASE}/datasets/${datasetId}/export/yolo`,
};

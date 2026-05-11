export interface Box {
  id?: number;
  cx: number;
  cy: number;
  w: number;
  h: number;
  class_idx: number;
  confidence: number | null;
  source: "human" | "model";
}

export interface ImageRecord {
  id: number;
  dataset_id: number;
  filename: string;
  width: number;
  height: number;
  status: "pending" | "labeled" | "predicted" | "reviewed" | "rejected";
  confidence: number | null;
  boxes: Box[];
}

export interface Dataset {
  id: number;
  name: string;
  class_name: string;
  created_at: string;
  image_count: number;
  labeled_count: number;
}

export interface TrainingRun {
  id: number;
  dataset_id: number;
  status: "queued" | "running" | "done" | "failed";
  epochs: number;
  started_at: string;
  finished_at: string | null;
  weights_path: string | null;
  log: string | null;
}

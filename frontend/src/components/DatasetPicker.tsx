import { useEffect, useState } from "react";
import type { Dataset } from "../types";
import { api } from "../api";

interface Props {
  current: Dataset | null;
  onSelect: (d: Dataset) => void;
}

export function DatasetPicker({ current, onSelect }: Props) {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [className, setClassName] = useState("object");

  async function refresh() {
    const rows = await api.listDatasets();
    setDatasets(rows);
    if (!current && rows.length > 0) onSelect(rows[0]);
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreate() {
    if (!name.trim()) return;
    const ds = await api.createDataset(name.trim(), className.trim() || "object");
    setName("");
    setClassName("object");
    setCreating(false);
    await refresh();
    onSelect(ds);
  }

  return (
    <div className="section">
      <h3>Datasets</h3>
      <div className="list">
        {datasets.map((d) => (
          <div
            key={d.id}
            className={`list-item ${current?.id === d.id ? "active" : ""}`}
            onClick={() => onSelect(d)}
          >
            <div>{d.name} <span className="badge">{d.class_name}</span></div>
            <div className="muted">
              {d.labeled_count}/{d.image_count} labeled
            </div>
          </div>
        ))}
      </div>

      {creating ? (
        <div className="col" style={{ marginTop: 8 }}>
          <input
            type="text"
            placeholder="dataset name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            type="text"
            placeholder="class name (e.g. defect)"
            value={className}
            onChange={(e) => setClassName(e.target.value)}
          />
          <div className="row">
            <button className="primary" onClick={handleCreate}>Create</button>
            <button className="ghost" onClick={() => setCreating(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        <button
          className="ghost"
          style={{ marginTop: 8, width: "100%" }}
          onClick={() => setCreating(true)}
        >
          + New dataset
        </button>
      )}
    </div>
  );
}

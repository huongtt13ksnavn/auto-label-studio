import { useEffect, useState, type MouseEvent } from "react";
import type { Dataset } from "../types";
import { api } from "../api";

interface Props {
  current: Dataset | null;
  onSelect: (d: Dataset | null) => void;
  /** Bump to force a re-fetch of the dataset list (e.g. after labels change). */
  refreshTick?: number;
}

function normalize(input: string): string[] {
  return input
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function DatasetPicker({ current, onSelect, refreshTick = 0 }: Props) {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [classes, setClasses] = useState<string[]>(["object"]);
  const [classInput, setClassInput] = useState("");

  async function refresh() {
    const rows = await api.listDatasets();
    setDatasets(rows);
    if (!current && rows.length > 0) onSelect(rows[0]);
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshTick]);

  function addClasses(raw: string) {
    const next = normalize(raw);
    if (next.length === 0) return;
    setClasses((cur) => {
      const seen = new Set(cur);
      const out = [...cur];
      for (const c of next) {
        if (!seen.has(c)) {
          seen.add(c);
          out.push(c);
        }
      }
      return out;
    });
    setClassInput("");
  }

  function removeClass(c: string) {
    setClasses((cur) => cur.filter((x) => x !== c));
  }

  async function handleCreate() {
    if (!name.trim()) return;
    const final = classes.length > 0 ? classes : ["object"];
    const ds = await api.createDataset(name.trim(), final);
    setName("");
    setClasses(["object"]);
    setClassInput("");
    setCreating(false);
    await refresh();
    onSelect(ds);
  }

  async function handleDelete(d: Dataset, ev: MouseEvent) {
    ev.stopPropagation();
    const msg =
      `Delete dataset "${d.name}"?\n\n` +
      `This permanently removes ${d.image_count} image(s), all labels, ` +
      `predictions, training runs, and weights on disk. ` +
      `Cannot be undone.`;
    if (!window.confirm(msg)) return;
    try {
      await api.deleteDataset(d.id);
    } catch (e: any) {
      window.alert(`Delete failed: ${e.message}`);
      return;
    }
    if (current?.id === d.id) onSelect(null);
    await refresh();
  }

  return (
    <div className="section">
      <h3>Datasets</h3>
      <div className="list">
        {datasets.map((d) => {
          const names = d.class_names || [];
          const label =
            names.length === 0
              ? "(no classes)"
              : names.length <= 2
              ? names.join(", ")
              : `${names[0]} +${names.length - 1}`;
          return (
            <div
              key={d.id}
              className={`list-item ${current?.id === d.id ? "active" : ""}`}
              onClick={() => onSelect(d)}
              title={names.join(", ")}
              style={{ position: "relative" }}
            >
              <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div>
                    {d.name} <span className="badge">{label}</span>
                  </div>
                  <div className="muted">
                    {d.labeled_count}/{d.image_count} labeled
                  </div>
                </div>
                <button
                  type="button"
                  className="ghost"
                  onClick={(ev) => handleDelete(d, ev)}
                  title={`Delete ${d.name}`}
                  aria-label={`Delete ${d.name}`}
                  style={{
                    padding: "2px 6px",
                    fontSize: 14,
                    lineHeight: 1,
                    color: "var(--muted)",
                  }}
                >
                  ×
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {creating ? (
        <div className="col" style={{ marginTop: 8 }}>
          <input
            type="text"
            placeholder="dataset name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />

          <div className="row" style={{ flexWrap: "wrap", gap: 4 }}>
            {classes.map((c) => (
              <span key={c} className="badge" style={{ cursor: "pointer" }}>
                {c}
                <button
                  type="button"
                  className="ghost"
                  style={{ marginLeft: 4, padding: "0 4px" }}
                  onClick={() => removeClass(c)}
                  aria-label={`remove ${c}`}
                >
                  ×
                </button>
              </span>
            ))}
          </div>

          <input
            type="text"
            placeholder="add class (Enter or comma)"
            value={classInput}
            onChange={(e) => setClassInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === ",") {
                e.preventDefault();
                addClasses(classInput);
              } else if (e.key === "Backspace" && classInput === "" && classes.length > 0) {
                removeClass(classes[classes.length - 1]);
              }
            }}
            onBlur={() => classInput && addClasses(classInput)}
          />

          <div className="row">
            <button className="primary" onClick={handleCreate}>
              Create
            </button>
            <button
              className="ghost"
              onClick={() => {
                setCreating(false);
                setClasses(["object"]);
                setClassInput("");
              }}
            >
              Cancel
            </button>
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

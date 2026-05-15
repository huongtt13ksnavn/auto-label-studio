import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type { Box, Dataset, ImageRecord } from "./types";
import { DatasetPicker } from "./components/DatasetPicker";
import { Upload } from "./components/Upload";
import { BboxCanvas } from "./components/BboxCanvas";
import { TrainingPanel } from "./components/TrainingPanel";
import { ClassPicker } from "./components/ClassPicker";
import { classColor, classLabel } from "./classColor";

type Mode = "label" | "review";

export default function App() {
  const [mode, setMode] = useState<Mode>("label");
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [images, setImages] = useState<ImageRecord[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [boxes, setBoxes] = useState<Box[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string>("");
  const [activeClassIdx, setActiveClassIdx] = useState(0);

  const classNames = dataset?.class_names ?? [];

  // reset active class when switching datasets
  useEffect(() => {
    setActiveClassIdx(0);
  }, [dataset?.id]);

  // refresh queue/images
  async function refreshImages(d: Dataset | null = dataset) {
    if (!d) return;
    try {
      const list =
        mode === "label"
          ? await api.listImages(d.id, "pending")
          : await api.queue(d.id, 200, "confidence_asc");
      setImages(list);
      setCurrentIdx(0);
    } catch (e: any) {
      setStatusMsg(`Load failed: ${e.message}`);
    }
  }

  useEffect(() => {
    refreshImages();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset?.id, mode]);

  const current = images[currentIdx] ?? null;

  // when current changes, seed boxes from server
  useEffect(() => {
    if (!current) {
      setBoxes([]);
      setSelectedIdx(null);
      setDirty(false);
      return;
    }
    setBoxes(current.boxes.map((b) => ({ ...b })));
    setSelectedIdx(null);
    setDirty(false);
  }, [current?.id]);

  const minConf = useMemo(() => {
    if (!current?.boxes.length) return null;
    const cs = current.boxes
      .map((b) => b.confidence)
      .filter((c): c is number => c != null);
    return cs.length ? Math.min(...cs) : null;
  }, [current]);

  async function save(status: "labeled" | "reviewed" | "rejected") {
    if (!current) return;
    try {
      const updated = await api.updateLabels(
        current.id,
        boxes.map(({ id, ...rest }) => rest),
        status
      );
      // remove from list (it moved out of the active filter)
      setImages((prev) => prev.filter((p) => p.id !== updated.id));
      setStatusMsg(
        status === "rejected"
          ? `Rejected #${updated.id}`
          : `Saved #${updated.id} (${updated.boxes.length} boxes)`
      );
      // index stays, so the next image slides in
    } catch (e: any) {
      setStatusMsg(`Save failed: ${e.message}`);
    }
  }

  async function approveAsIs() {
    if (!current) return;
    // keep predicted boxes as-is, mark reviewed
    try {
      const updated = await api.updateLabels(
        current.id,
        boxes.map(({ id, ...rest }) => ({ ...rest, source: "human" as const })),
        "reviewed"
      );
      setImages((prev) => prev.filter((p) => p.id !== updated.id));
      setStatusMsg(`Approved #${updated.id}`);
    } catch (e: any) {
      setStatusMsg(`Approve failed: ${e.message}`);
    }
  }

  // keyboard shortcuts
  const boxesRef = useRef(boxes);
  boxesRef.current = boxes;
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;

      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setCurrentIdx((i) => Math.min(images.length - 1, i + 1));
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setCurrentIdx((i) => Math.max(0, i - 1));
      } else if (e.key === "a") {
        e.preventDefault();
        mode === "review" ? approveAsIs() : save("labeled");
      } else if (e.key === "e") {
        e.preventDefault();
        save(mode === "review" ? "reviewed" : "labeled");
      } else if (e.key === "r") {
        e.preventDefault();
        save("rejected");
      } else if (/^[1-9]$/.test(e.key)) {
        const idx = parseInt(e.key, 10) - 1;
        const names = dataset?.class_names ?? [];
        if (idx < names.length) {
          e.preventDefault();
          setActiveClassIdx(idx);
          // if a box is selected, reassign its class
          if (selectedIdx !== null) {
            setBoxes((prev) => {
              if (selectedIdx < 0 || selectedIdx >= prev.length) return prev;
              const copy = prev.slice();
              copy[selectedIdx] = { ...copy[selectedIdx], class_idx: idx, source: "human" };
              return copy;
            });
            setDirty(true);
          }
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [images, currentIdx, mode, dataset?.id, selectedIdx]);

  return (
    <div className="app">
      <header className="topbar">
        <h1>auto-label-studio</h1>
        <div className="nav">
          <button
            className={mode === "label" ? "active" : ""}
            onClick={() => setMode("label")}
          >
            Label
          </button>
          <button
            className={mode === "review" ? "active" : ""}
            onClick={() => setMode("review")}
          >
            Review
          </button>
        </div>
        <div className="spacer" />
        <div className="muted">
          {dataset
            ? `${dataset.name} • ${dataset.labeled_count}/${dataset.image_count}`
            : "no dataset"}
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <DatasetPicker current={dataset} onSelect={setDataset} />
          {dataset && (
            <>
              <Upload datasetId={dataset.id} onUploaded={() => refreshImages()} />
              <TrainingPanel dataset={dataset} onRefresh={() => refreshImages()} />
            </>
          )}
        </aside>

        <main className="main">
          <div className="canvas-wrap">
            {!dataset && (
              <div className="muted">Create or select a dataset to begin.</div>
            )}
            {dataset && !current && (
              <div className="muted">
                {mode === "label"
                  ? "No pending images. Upload some, or switch to Review."
                  : "Review queue empty. Train and predict to populate it."}
              </div>
            )}
            {dataset && current && (
              <BboxCanvas
                image={current}
                imageUrl={api.imageUrl(current.id)}
                boxes={boxes}
                onChange={(b) => {
                  setBoxes(b);
                  setDirty(true);
                }}
                selectedIdx={selectedIdx}
                setSelectedIdx={setSelectedIdx}
                classNames={classNames}
                activeClassIdx={activeClassIdx}
              />
            )}
          </div>
          <footer className="statusbar">
            <span>
              {current ? `#${current.id} (${currentIdx + 1}/${images.length})` : "—"}
            </span>
            {minConf != null && (
              <span
                className={`conf-pill ${
                  minConf < 0.4 ? "conf-low" : minConf < 0.7 ? "conf-mid" : "conf-hi"
                }`}
              >
                min conf {(minConf * 100).toFixed(0)}%
              </span>
            )}
            <span className="spacer" style={{ flex: 1 }} />
            <span>{statusMsg}</span>
          </footer>
        </main>

        <aside className="rightbar">
          {dataset && classNames.length > 0 && (
            <ClassPicker
              classNames={classNames}
              activeIdx={activeClassIdx}
              onSelect={(idx) => {
                setActiveClassIdx(idx);
                if (selectedIdx !== null) {
                  setBoxes((prev) => {
                    if (selectedIdx < 0 || selectedIdx >= prev.length) return prev;
                    const copy = prev.slice();
                    copy[selectedIdx] = {
                      ...copy[selectedIdx],
                      class_idx: idx,
                      source: "human",
                    };
                    return copy;
                  });
                  setDirty(true);
                }
              }}
            />
          )}

          <div className="section">
            <h3>Boxes ({boxes.length})</h3>
            <div className="list">
              {boxes.length === 0 && <div className="muted">Drag on the image to draw.</div>}
              {boxes.map((b, i) => {
                const color = classColor(b.class_idx);
                const name = classLabel(b.class_idx, classNames);
                return (
                  <div
                    key={i}
                    className={`list-item ${selectedIdx === i ? "active" : ""}`}
                    onClick={() => setSelectedIdx(i)}
                  >
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <div className="row" style={{ gap: 6 }}>
                        <span
                          aria-hidden
                          style={{
                            display: "inline-block",
                            width: 8,
                            height: 8,
                            borderRadius: 2,
                            background: color,
                          }}
                        />
                        <span style={{ color, fontSize: 12 }}>{name}</span>
                      </div>
                      <span className="muted" style={{ fontSize: 11 }}>
                        {b.source}
                        {b.confidence != null && ` ${(b.confidence * 100).toFixed(0)}%`}
                      </span>
                    </div>
                    {classNames.length > 1 && (
                      <select
                        value={b.class_idx}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => {
                          const next = parseInt(e.target.value, 10);
                          setBoxes((prev) => {
                            const copy = prev.slice();
                            copy[i] = { ...copy[i], class_idx: next, source: "human" };
                            return copy;
                          });
                          setDirty(true);
                        }}
                        style={{ marginTop: 6, fontSize: 12 }}
                      >
                        {classNames.map((n, ci) => (
                          <option key={ci} value={ci}>
                            {ci + 1}. {n}
                          </option>
                        ))}
                      </select>
                    )}
                    <div className="muted" style={{ marginTop: 4 }}>
                      {b.w.toFixed(2)} × {b.h.toFixed(2)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="section">
            <h3>Actions</h3>
            {mode === "label" ? (
              <div className="col">
                <button className="primary" onClick={() => save("labeled")}>
                  Save <span className="kbd">A</span> / <span className="kbd">E</span>
                </button>
                <button className="ghost" onClick={() => save("rejected")}>
                  Reject <span className="kbd">R</span>
                </button>
              </div>
            ) : (
              <div className="col">
                <button className="primary" onClick={approveAsIs}>
                  Approve <span className="kbd">A</span>
                </button>
                <button className="ghost" onClick={() => save("reviewed")}>
                  Save edits <span className="kbd">E</span>
                </button>
                <button className="ghost" onClick={() => save("rejected")}>
                  Reject <span className="kbd">R</span>
                </button>
              </div>
            )}
          </div>

          <div className="section">
            <h3>Shortcuts</h3>
            <div className="muted">
              <div><span className="kbd">J</span> / <span className="kbd">↓</span> next</div>
              <div><span className="kbd">K</span> / <span className="kbd">↑</span> prev</div>
              <div><span className="kbd">A</span> approve</div>
              <div><span className="kbd">E</span> save edits</div>
              <div><span className="kbd">R</span> reject</div>
              <div><span className="kbd">Del</span> remove selected box</div>
              <div>
                <span className="kbd">1</span>–<span className="kbd">9</span> pick class
                (also reassigns selected box)
              </div>
            </div>
          </div>

          {dirty && <div className="muted">Unsaved changes…</div>}
        </aside>
      </div>
    </div>
  );
}

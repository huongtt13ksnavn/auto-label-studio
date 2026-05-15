import { useEffect, useState } from "react";
import { api } from "../api";
import type { Dataset, TrainingRun } from "../types";

interface Props {
  dataset: Dataset;
  onRefresh: () => void;
}

export function TrainingPanel({ dataset, onRefresh }: Props) {
  const [runs, setRuns] = useState<TrainingRun[]>([]);
  const [epochs, setEpochs] = useState(20);
  const [conf, setConf] = useState(0.25);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      setRuns(await api.listRuns(dataset.id));
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset.id]);

  async function train() {
    setBusy(true);
    setMsg(null);
    try {
      await api.startTrain(dataset.id, epochs);
      setMsg(`Training queued (${epochs} epochs).`);
      refresh();
    } catch (e: any) {
      setMsg(`Train failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function removeRun(runId: number, status: string) {
    const verb = status === "failed" ? "Remove" : "Delete";
    if (!window.confirm(
      `${verb} run #${runId}? Weights and training artifacts on disk will also be removed.`
    )) return;
    try {
      await api.deleteRun(runId);
      setMsg(`Removed run #${runId}.`);
      refresh();
      onRefresh();
    } catch (e: any) {
      setMsg(`Remove failed: ${e.message}`);
    }
  }

  async function predict() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.predictUnlabeled(dataset.id, conf);
      setMsg(`Predicting ${r.queued} image(s) in background.`);
      onRefresh();
    } catch (e: any) {
      setMsg(`Predict failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  const latest = runs[0];

  return (
    <div className="section">
      <h3>Train + predict</h3>

      <div className="col">
        <label className="muted">Epochs</label>
        <input
          type="number"
          min={1}
          max={300}
          value={epochs}
          onChange={(e) => setEpochs(parseInt(e.target.value || "20", 10))}
        />
        <button className="primary" disabled={busy} onClick={train}>
          Train on labeled
        </button>

        <label className="muted">Conf threshold</label>
        <input
          type="number"
          min={0}
          max={1}
          step={0.05}
          value={conf}
          onChange={(e) => setConf(parseFloat(e.target.value || "0.25"))}
        />
        <button className="ghost" disabled={busy} onClick={predict}>
          Predict pending images
        </button>

        {msg && <div className="muted">{msg}</div>}
      </div>

      <div className="section" style={{ marginTop: 16 }}>
        <h3>Runs</h3>
        {runs.length === 0 && <div className="muted">No runs yet.</div>}
        <div className="list">
          {runs.map((r) => (
            <div key={r.id} className="list-item">
              <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div>
                    #{r.id} <span className="badge">{r.status}</span>
                  </div>
                  <div className="muted">
                    {r.epochs} epochs • {r.finished_at ? "done" : "running"}
                  </div>
                  {r.log && <div className="muted">{r.log}</div>}
                </div>
                {r.status !== "running" && (
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => removeRun(r.id, r.status)}
                    title={`Remove run #${r.id}`}
                    aria-label={`Remove run #${r.id}`}
                    style={{
                      padding: "2px 6px",
                      fontSize: 14,
                      lineHeight: 1,
                      color: "var(--muted)",
                    }}
                  >
                    ×
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
        <a
          href={api.exportYoloUrl(dataset.id)}
          target="_blank"
          rel="noreferrer"
        >
          <button className="ghost" style={{ width: "100%", marginTop: 8 }}>
            Export YOLO .zip
          </button>
        </a>
        {!latest && (
          <div className="muted" style={{ marginTop: 6 }}>
            Tip: export works on labeled images even before training.
          </div>
        )}
      </div>
    </div>
  );
}

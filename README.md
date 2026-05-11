# auto-label-studio

Active-learning image labeling tool. Pre-product MVP. **2-week build target.**

Pitch: "Label 50, auto-label 500." Self-hosted, offline, free. See [design-mvp-20260511.md](./design-mvp-20260511.md) for full design doc including risks and assumptions.

> ⚠️ The "Label 50 → auto-label 500" claim is **unverified on custom domains**. YOLOv5n typically needs 200-500 samples to generalize. Validate on real data before promising it externally.
>
> ⚠️ The name `auto-label-studio` collides with the existing **Label Studio** project. Rename before any public launch (suggestions: `Loop`, `Quickref`, `Seedlabel`, `Tinylabel`).

---

## Architecture

```
auto-label-studio/
├── backend/             FastAPI + SQLAlchemy + SQLite + ultralytics
│   ├── main.py          app + CORS + router
│   ├── db.py            engine, session, init_db
│   ├── models.py        ORM: Dataset, Image, Box, TrainingRun
│   ├── schemas.py       Pydantic IO models
│   ├── routes.py        REST endpoints
│   ├── ml.py            pluggable model backend (default: ultralytics)
│   └── requirements.txt
├── frontend/            React + Vite + TypeScript + react-konva
│   └── src/
│       ├── App.tsx
│       ├── api.ts
│       ├── types.ts
│       ├── styles.css
│       └── components/
│           ├── BboxCanvas.tsx
│           ├── DatasetPicker.tsx
│           ├── TrainingPanel.tsx
│           └── Upload.tsx
├── data/                runtime SQLite + uploaded images (gitignored)
├── models/              cached pretrained weights (gitignored)
└── runs/                training run artifacts (gitignored)
```

## Workflow

1. Create dataset (single class)
2. Upload images
3. Manually draw bboxes on 50+ images (the "seed")
4. Click **Train on labeled** — fine-tunes YOLOv5n in the background
5. Click **Predict pending images** — auto-labels remaining images
6. Switch to **Review** tab — queue sorted by lowest confidence first
7. Approve / edit / reject; retrain when you've reviewed a batch
8. **Export YOLO .zip** when satisfied

## Run locally

### One command (recommended)

**Windows (PowerShell):**
```powershell
.\run.ps1                  # full launch, installs deps on first run
.\run.ps1 -SkipInstall     # fast restart
.\run.ps1 -BackendPort 8001
```

If you hit `running scripts is disabled` once:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

**macOS / Linux:**
```bash
chmod +x run.sh
./run.sh                   # full launch
./run.sh --skip-install    # fast restart
BACKEND_PORT=8001 ./run.sh
```

Both scripts:
- Create `backend/.venv` and install `requirements.txt` if missing
- Run `npm install` in `frontend/` if missing
- Stream backend + frontend output to one terminal
- Stop both cleanly on Ctrl+C

> First-time install is slow — `torch` is ~750MB. First training run also downloads `yolov5nu.pt` (~5MB) from Ultralytics.

### Manual (if you want separate terminals)

Backend (Python 3.11+):
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend (Node 20+):
```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api/*` → `http://127.0.0.1:8000`.

## API surface

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/datasets` | Create dataset |
| `GET` | `/api/datasets` | List datasets |
| `POST` | `/api/datasets/{id}/upload` | Multipart image upload |
| `GET` | `/api/datasets/{id}/images?status=pending` | List images |
| `GET` | `/api/images/{id}/file` | Serve image bytes |
| `PUT` | `/api/images/{id}/labels` | Save bboxes + status |
| `POST` | `/api/datasets/{id}/train` | Trigger fine-tune (background) |
| `GET` | `/api/datasets/{id}/runs` | List training runs |
| `POST` | `/api/datasets/{id}/predict` | Predict pending images (background) |
| `GET` | `/api/datasets/{id}/queue?sort=confidence_asc` | Review queue |
| `GET` | `/api/datasets/{id}/export/yolo` | Download YOLO `.zip` |

Open `http://127.0.0.1:8000/docs` for the Swagger UI.

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `J` / `↓` | Next image |
| `K` / `↑` | Previous image |
| `A` | Approve (review) / Save labels (label mode) |
| `E` | Save edits |
| `R` | Reject |
| `Del` / `Backspace` | Delete selected bbox |
| Click-drag on image | Draw new bbox |
| Click bbox | Select |
| Drag selected bbox | Move |

## License caveats

- **YOLOv5 / YOLOv8 (Ultralytics) = AGPL-3.0.** Self-hosted internal use does not trigger AGPL distribution clauses. If you redistribute a binary or host this as a SaaS, audit your license obligations.
- **Swap path:** `backend/ml.py` defines a `ModelBackend` abstract class. Implement against torchvision FasterRCNN (BSD), detectron2 (Apache 2.0), or a pre-AGPL YOLOv5 fork to remove the AGPL dependency.

## Known limitations (MVP)

- Single-class detection only (multi-class deferred)
- No multi-user / auth
- No audit log, no inter-annotator agreement
- Export limited to YOLO (no COCO / Pascal VOC / JSONL yet)
- No video / 3D / NER support
- SQLite — fine for solo use, swap to Postgres for multi-annotator

## Next steps (post-MVP)

1. **5 user interviews this week.** Validate (a) Label Studio's ML-backend setup is the actual pain, (b) the "Label 50" promise survives contact with real data.
2. **Rename project** before any public mention.
3. **Multi-class support** (most real domains have 3-15 classes).
4. **Active-learning loop UX**: surface "training would improve queue confidence by ~N%" hints based on current label distribution.
5. Consider scoping to **Label Studio ML backend plugin** if interviews show distribution > standalone product matters more.

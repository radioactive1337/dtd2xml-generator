# QA XML Generator Tool

Local QA tool for generating XML documents from large DTD schemas.

## Setup

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

### Configuration

Copy `backend/connections.json.example` to `connections.json` in the project root (or `backend/connections.json`).
**Never commit real credentials.**

## Run

### Development (two terminals)

```bash
# Terminal 1 — API on port 8080
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

# Terminal 2 — UI on port 5173
cd frontend
npm run dev
```

Open http://localhost:5173

### Production (single process)

```bash
cd frontend && npm run build
cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open http://localhost:8080

## Tests

```bash
cd backend
pytest tests/ -v
```

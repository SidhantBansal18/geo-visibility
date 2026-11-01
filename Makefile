.PHONY: install dev demo api web test

install:
	cd backend && uv sync
	cd frontend && npm install

# Real engines (reads backend/.env)
api:
	cd backend && PYTHONPATH=. uv run uvicorn app.main:app --reload --port 8000

web:
	cd frontend && npm run dev

# Offline demo with simulated AI answers
demo:
	cd backend && GEO_MOCK=1 PYTHONPATH=. uv run uvicorn app.main:app --reload --port 8000 & \
	cd frontend && npm run dev

test:
	cd backend && uv run pytest -q
	cd frontend && npx tsc --noEmit

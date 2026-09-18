import pathlib, subprocess

ROOT = pathlib.Path.cwd()
DOCKER = ROOT / "docker"
DOCKER.mkdir(exist_ok=True)

F = {}

F["docker-compose.yml"] = """version: "3.9"

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-airouter}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-airouter_dev}
      POSTGRES_DB: ${POSTGRES_DB:-airouter}
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-airouter}"]
      interval: 5s
      timeout: 3s
      retries: 20

  api:
    build:
      context: .
      dockerfile: docker/Dockerfile
    depends_on:
      db:
        condition: service_healthy
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://${POSTGRES_USER:-airouter}:${POSTGRES_PASSWORD:-airouter_dev}@db:5432/${POSTGRES_DB:-airouter}
    volumes:
      - ./sessions:/app/sessions
      - ./logs:/app/logs
      - ./.ainterceptor:/app/.ainterceptor
    ports:
      - "8000:8000"
    restart: unless-stopped
    command: >
      sh -c "alembic -c /app/alembic.ini upgrade head &&
             uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"
"""

F["docker/Dockerfile"] = """FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \\
    PYTHONDONTWRITEBYTECODE=1 \\
    PIP_NO_CACHE_DIR=1 \\
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update && apt-get install -y --no-install-recommends \\
    curl ca-certificates \\
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \\
    libdbus-1-3 libxkbcommon0 libatspi2.0-0 libxcomposite1 \\
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \\
    libcairo2 libasound2 \\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip && pip install -r backend/requirements.txt
RUN python -m playwright install --with-deps chromium

COPY . /app/

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s \\
  CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
"""

F[".dockerignore"] = """.git
.github
.evidence
.ainterceptor
sessions
logs
data
node_modules
dashboard
__pycache__
*.pyc
*.pyo
.venv
venv
.pytest_cache
scripts/bootstrap
docs
tests/test_*.py
*.md
_bundle.zip
"""

F[".env.example"] = """# AInterceptor — environment file
# Copy to .env and fill in the two required secrets.
# NEVER commit .env.

# 32 random bytes, base64-encoded. Generate with:
#   python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
MASTER_KEY=

# Random string, at least 32 chars
JWT_SECRET=

# Postgres
POSTGRES_USER=airouter
POSTGRES_PASSWORD=airouter_dev
POSTGRES_DB=airouter
DATABASE_URL=postgresql+psycopg://airouter:airouter_dev@db:5432/airouter

# Logging
LOG_LEVEL=INFO
"""

F["backend/requirements.txt"] = """fastapi==0.115.0
uvicorn[standard]==0.32.0
httpx==0.27.2
pydantic==2.9.2
pydantic-settings==2.5.2
sqlalchemy==2.0.36
alembic==1.13.3
psycopg[binary]==3.2.3
pyjwt==2.9.0
argon2-cffi==23.1.0
cryptography==43.0.3
python-multipart==0.0.12
playwright==1.48.0
pytest==8.3.3
pytest-asyncio==0.24.0
"""

for rel, txt in F.items():
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8", newline="\n")
    print(f"  [OK] {rel}  ({len(txt)} B)")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","feat(phase-1): docker stack (compose, Dockerfile, env, requirements)"])
print((r.stdout.strip() or r.stderr.strip())[:400])
print("DONE — script 1/6. Run script 2 next.")

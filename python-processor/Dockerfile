FROM python:3.11.13-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
  && apt-get install --no-install-recommends --yes postgresql-client \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --system --uid 10003 --create-home backend \
  && mkdir -p /app/uploads /app/recordings \
  && chown -R backend:backend /app

FROM base AS test
RUN pip install --no-cache-dir pytest coverage ruff
RUN PYTHONPATH=/app python -m pytest -q

FROM base AS runtime
USER backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

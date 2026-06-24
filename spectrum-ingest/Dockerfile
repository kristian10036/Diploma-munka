FROM python:3.11.13-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

FROM base AS test
COPY test_app.py .
RUN pip install --no-cache-dir pytest
RUN python -m pytest -q test_app.py

FROM base AS runtime

RUN useradd --system --uid 10002 --create-home ingest
USER ingest
EXPOSE 8001 9998/udp
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY libs/kvyt_common /tmp/kvyt_common
COPY seed/pyproject.toml /tmp/seed/pyproject.toml
RUN pip install --no-cache-dir /tmp/kvyt_common /tmp/seed && rm -rf /tmp/kvyt_common /tmp/seed

COPY seed/seed.py /app/seed.py

CMD ["python", "/app/seed.py"]

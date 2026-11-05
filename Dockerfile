FROM python:3.15-slim@sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && python -m pip install --no-deps setuptools==78.1.1 \
    && python -m pip uninstall -y setuptools wheel \
    && rm -rf /usr/local/lib/python3.12/site-packages/pip /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12

COPY . .

RUN chmod +x /app/docker/backend-entrypoint.sh

# Non-root runtime user. The entrypoint runs as root only to make Docker
# Compose secrets readable, then drops to this user before starting uvicorn.
RUN useradd --create-home --shell /usr/sbin/nologin --uid 1000 appuser

EXPOSE 8000

ENTRYPOINT ["/app/docker/backend-entrypoint.sh"]
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

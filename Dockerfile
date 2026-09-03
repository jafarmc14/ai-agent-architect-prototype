FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && python -m pip install --no-deps setuptools==78.1.1 \
    && python -m pip uninstall -y setuptools wheel \
    && rm -rf /usr/local/lib/python3.12/site-packages/pip /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12

COPY . .

RUN chmod +x /app/docker/backend-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker/backend-entrypoint.sh"]
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

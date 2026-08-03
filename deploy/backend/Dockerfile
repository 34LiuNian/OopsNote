FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml /app/
COPY --chown=10001:10001 oopsnote /app/oopsnote
COPY --chown=10001:10001 skills /app/skills
COPY deploy/backend/entrypoint.sh /usr/local/bin/oopsnote-entrypoint
RUN pip install --no-cache-dir .
RUN apt-get update \
    && apt-get install --no-install-recommends -y gosu \
    && rm -rf /var/lib/apt/lists/* \
    && chmod 0755 /usr/local/bin/oopsnote-entrypoint \
    && useradd --system --uid 10001 --create-home oopsnote \
    && mkdir -p /data /vault \
    && chown oopsnote:oopsnote /data /vault \
    && chmod 700 /vault
ENV OOPSNOTE_STORAGE_DIR=/data
EXPOSE 8000
ENTRYPOINT ["oopsnote-entrypoint"]
CMD ["uvicorn", "oopsnote.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

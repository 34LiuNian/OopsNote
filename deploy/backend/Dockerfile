FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml /app/
COPY --chown=10001:10001 oopsnote /app/oopsnote
COPY --chown=10001:10001 skills /app/skills
RUN pip install --no-cache-dir .
RUN useradd --system --uid 10001 --create-home oopsnote \
    && mkdir -p /data \
    && chown oopsnote:oopsnote /data
USER oopsnote
ENV OOPSNOTE_STORAGE_DIR=/data
EXPOSE 8000
CMD ["uvicorn", "oopsnote.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

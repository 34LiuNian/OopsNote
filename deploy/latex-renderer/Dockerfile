FROM texlive/texlive:latest

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-fastapi python3-uvicorn fonts-noto-cjk \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py /app/app.py
RUN useradd --system --uid 10001 --create-home renderer
USER renderer
EXPOSE 8080
CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]

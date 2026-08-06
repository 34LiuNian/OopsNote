# LaTeX/TikZ renderer switching

`OOPSNOTE_LATEX_RENDERER_URL` is the only renderer selection setting. The
backend always sends the same `PaperBundle` or TikZ request to that URL.

## Windows backend, Docker renderer

Start only the renderer container from the development Compose stack. The
development override binds it to loopback so a native Windows backend can
reach it:

```powershell
docker compose -f docker-compose.dev.yml up -d --build latex-renderer
uvicorn oopsnote.api.main:app --env-file deploy/latex-renderer/.env.local.example --reload
```

Use a copied `.env.local` file for local changes; the checked-in example is
safe to use as-is.

## Full Docker stack

The Compose backend uses the internal service name. Keep this value when the
backend itself runs in Compose:

```dotenv
OOPSNOTE_LATEX_RENDERER_URL=http://latex-renderer:8080
```

Production Compose does not publish the renderer port.

## Probe

Verify the renderer before testing the paper workflow:

```powershell
Invoke-RestMethod http://127.0.0.1:18080/health
Invoke-WebRequest http://127.0.0.1:18080/v1/tikz `
  -Method Post -ContentType 'application/json' `
  -Body '{"source":"\\draw (0,0) -- (1,1);"}'
```

The health response must report `xelatex` and `dvisvgm` paths, and the TikZ
request must return `image/svg+xml`.

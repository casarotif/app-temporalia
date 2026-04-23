from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from apiclima.clima import clima_atual_por_cidade_cache_swr

logger = logging.getLogger("api-tempo")

app = FastAPI(title="API Tempo")

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/clima")
def api_clima(cidade: str, country_code: Optional[str] = None):
    try:
        return clima_atual_por_cidade_cache_swr(cidade, country_code=country_code)
    except (ValueError, LookupError) as e:
        # Erro de entrada/consulta: devolve mensagem curta e segura ao cliente.
        raise HTTPException(status_code=400, detail="Parâmetros inválidos ou cidade não encontrada.") from e
    except RuntimeError as e:
        # Evita expor detalhes internos/HTTP upstream ao cliente.
        logger.exception("Falha ao consultar Open-Meteo")
        raise HTTPException(status_code=502, detail="Falha ao consultar provedor de dados.") from e

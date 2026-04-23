"""Busca clima atual na Open-Meteo a partir do nome da cidade."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_CURRENT_PARAMS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
]

_CACHE_VERSION = 1
_SWR_REFRESH_LOCKS: dict[str, threading.Lock] = {}
_SWR_REFRESH_LOCKS_GUARD = threading.Lock()
_LOGGER = logging.getLogger("api-tempo")


def _get_json(
    url: str,
    params: Mapping[str, str | int | float],
    *,
    timeout: float = 10.0,
) -> dict[str, Any]:
    query = urlencode(params)
    full_url = f"{url}?{query}"

    req = Request(full_url, headers={"User-Agent": "api-tempo/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except HTTPError as e:
        # Tenta incluir o corpo para facilitar debugging (quando a API retorna JSON de erro).
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = str(e)
        raise RuntimeError(f"Erro Open-Meteo ({e.code}): {body}") from e
    except URLError as e:
        raise RuntimeError(f"Falha de rede ao chamar Open-Meteo: {e}") from e

    data = json.loads(body)
    if not isinstance(data, dict):
        raise RuntimeError(
            f"Resposta inesperada da API (não é objeto JSON). URL: {full_url}"
        )
    return data


def _default_cache_dir(app_name: str = "api-tempo") -> Path:
    """
    Retorna um diretório de cache multiplataforma (sem dependências externas).

    - Windows: %LOCALAPPDATA%\\<app_name>\\Cache (fallback: temp)
    - macOS: ~/Library/Caches/<app_name>
    - Linux/Unix: $XDG_CACHE_HOME/<app_name> (fallback: ~/.cache/<app_name>)
    """
    # Windows
    localapp = os.getenv("LOCALAPPDATA")
    if localapp:
        return Path(localapp) / app_name / "Cache"

    # macOS
    if sys.platform == "darwin":
        try:
            return Path.home() / "Library" / "Caches" / app_name
        except Exception:
            return Path(tempfile.gettempdir()) / app_name / "Cache"

    # Linux/Unix
    xdg = os.getenv("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / app_name
    try:
        return Path.home() / ".cache" / app_name
    except Exception:
        return Path(tempfile.gettempdir()) / app_name / "Cache"


def _cache_key_for_clima(
    nome_cidade: str,
    *,
    language: str,
    country_code: Optional[str],
) -> str:
    cc = (country_code or "").strip().upper()
    parts = {
        "v": _CACHE_VERSION,
        "nome": (nome_cidade or "").strip(),
        "language": (language or "").strip(),
        "country_code": cc,
        "current_params": _CURRENT_PARAMS,
    }
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"clima_{key}.json"


def _read_cache_file(path: Path) -> Optional[dict[str, Any]]:
    try:
        txt = path.read_text(encoding="utf-8")
        payload = json.loads(txt)
        if not isinstance(payload, dict):
            return None
        if not isinstance(payload.get("saved_at"), (int, float)):
            return None
        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        return payload
    except FileNotFoundError:
        return None
    except Exception:
        # Cache corrompido: trata como "miss".
        return None


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _get_refresh_lock(key: str) -> threading.Lock:
    with _SWR_REFRESH_LOCKS_GUARD:
        lock = _SWR_REFRESH_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _SWR_REFRESH_LOCKS[key] = lock
        return lock


def _spawn_revalidate(
    *,
    key: str,
    cache_file: Path,
    fetch_fn,
) -> None:
    lock = _get_refresh_lock(key)
    if lock.locked():
        return

    def _runner() -> None:
        if not lock.acquire(blocking=False):
            return
        try:
            data = fetch_fn()
            _atomic_write_json(
                cache_file,
                {"saved_at": time.time(), "data": data},
            )
        except Exception:
            # SWR: falhas de revalidação não devem quebrar quem está consumindo cache.
            _LOGGER.exception("Falha na revalidação SWR (cache não atualizado)")
        finally:
            lock.release()

    threading.Thread(target=_runner, name=f"swr-revalidate-{key[:8]}", daemon=True).start()


def clima_atual_por_cidade(
    nome_cidade: str,
    *,
    language: str = "pt",
    country_code: Optional[str] = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """
    Busca o clima atual a partir do nome de uma cidade.

    A função resolve a cidade via **geocoding** da Open-Meteo e, em seguida,
    consulta o endpoint de **forecast** para obter o bloco `current` nas
    coordenadas do primeiro resultado retornado.

    Parameters
    ----------
    nome_cidade:
        Nome da cidade a pesquisar (ex.: ``"São Paulo"``). O valor é normalizado
        com ``strip()`` e deve ter ao menos 2 caracteres.
    language:
        Idioma usado pelo geocoding para nomes de localidades (ex.: ``"pt"``,
        ``"en"``). Não pode ser vazio.
    country_code:
        Código do país (ISO 3166-1 alpha-2) para restringir a busca (ex.: ``"BR"``).
        Se ``None`` ou string vazia, não restringe.
    timeout:
        Tempo máximo (em segundos) para cada chamada HTTP à Open-Meteo.

    Returns
    -------
    dict[str, Any]
        Dicionário com três chaves:

        - ``"local"``: metadados da localidade resolvida
          (``nome``, ``pais``, ``regiao``, ``latitude``, ``longitude``).
        - ``"atual"``: bloco ``current`` retornado pela Open-Meteo.
        - ``"unidades"``: bloco ``current_units`` correspondente.

    Raises
    ------
    ValueError
        Se ``nome_cidade`` for muito curto ou se ``language`` estiver vazio.
    LookupError
        Se a cidade não for encontrada ou se o geocoding não retornar coordenadas válidas.
    RuntimeError
        Se ocorrer falha de rede/HTTP ao chamar a Open-Meteo, ou se o forecast não
        retornar os campos esperados.

    Examples
    --------
    >>> from apiclima.clima import clima_atual_por_cidade
    >>> resp = clima_atual_por_cidade("Curitiba", country_code="BR")
    >>> resp["local"]["nome"]
    'Curitiba'
    >>> round(resp["atual"]["temperature_2m"], 1)  # doctest: +SKIP
    18.7
    """
    nome = (nome_cidade or "").strip()
    if len(nome) < 2:
        raise ValueError("Nome da cidade muito curto (mínimo 2 caracteres).")

    lang = (language or "").strip()
    if not lang:
        raise ValueError('Parâmetro "language" não pode ser vazio.')

    geo_params: dict[str, str | int] = {
        "name": nome,
        "count": 1,
        "language": lang,
    }
    if country_code is not None:
        cc = country_code.strip().upper()
        if cc:
            geo_params["countryCode"] = cc

    data_geo = _get_json(GEOCODING_URL, geo_params, timeout=timeout)

    results = data_geo.get("results") or []
    if not results:
        extra = f" (country_code={geo_params.get('countryCode')})" if geo_params.get("countryCode") else ""
        raise LookupError(f'Cidade não encontrada: "{nome}"{extra}')

    loc = results[0]
    try:
        lat = float(loc["latitude"])
        lon = float(loc["longitude"])
    except (KeyError, TypeError, ValueError):
        raise LookupError(
            f'A geocodificação não devolveu coordenadas válidas para "{nome_cidade}".'
        ) from None

    fc_params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join(_CURRENT_PARAMS),
        "timezone": "auto",
    }

    forecast = _get_json(FORECAST_URL, fc_params, timeout=timeout)
    atual = forecast.get("current")
    unidades = forecast.get("current_units")
    if not isinstance(atual, dict) or not isinstance(unidades, dict):
        raise RuntimeError(
            'Resposta inesperada do forecast (campos "current"/"current_units" ausentes ou inválidos).'
        )

    return {
        "local": {
            "nome": loc.get("name"),
            "pais": loc.get("country"),
            "regiao": loc.get("admin1"),
            "latitude": lat,
            "longitude": lon,
        },
        "atual": atual,
        "unidades": unidades,
    }


def clima_atual_por_cidade_cache_swr(
    nome_cidade: str,
    *,
    language: str = "pt",
    country_code: Optional[str] = None,
    timeout: float = 10.0,
    cache_dir: Optional[str | os.PathLike[str]] = None,
    ttl_seconds: float = 3600.0,
    stale_max_seconds: float = 6 * 3600.0,
) -> dict[str, Any]:
    """
    Cacheia por 1h (TTL) e aplica SWR (stale-while-revalidate).

    - Se o cache ainda é válido (idade <= TTL): retorna cache imediatamente.
    - Se está "stale" (TTL < idade <= stale_max): retorna cache imediatamente e
      dispara revalidação em background.
    - Se não há cache (ou está velho demais): busca na API de forma bloqueante e
      atualiza o cache.

    O cache é persistido em disco, em um diretório multiplataforma.
    """
    cache_base = Path(cache_dir) if cache_dir is not None else _default_cache_dir()
    key = _cache_key_for_clima(
        nome_cidade,
        language=language,
        country_code=country_code,
    )
    cache_file = _cache_path(cache_base, key)

    def _fetch() -> dict[str, Any]:
        return clima_atual_por_cidade(
            nome_cidade,
            language=language,
            country_code=country_code,
            timeout=timeout,
        )

    now = time.time()
    cached = _read_cache_file(cache_file)
    if cached is not None:
        age = now - float(cached["saved_at"])
        if age <= ttl_seconds:
            return cached["data"]
        if age <= stale_max_seconds:
            _spawn_revalidate(key=key, cache_file=cache_file, fetch_fn=_fetch)
            return cached["data"]

    data = _fetch()
    try:
        _atomic_write_json(cache_file, {"saved_at": now, "data": data})
    except Exception:
        # Se falhar ao persistir, ainda devolve o dado "fresh".
        _LOGGER.exception("Falha ao gravar cache em disco (seguindo sem cache)")
    return data

"""Testes para clima_atual_por_cidade e _get_json (mocks, sem rede por padrão)."""

from __future__ import annotations

import json
import os
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

from urllib.error import HTTPError, URLError


class _HTTPErrorCorpoIlegivel(HTTPError):
    """HTTPError cujo read() falha (simula corpo inacessível)."""

    def __init__(self) -> None:
        super().__init__("https://example.com", 502, "Bad Gateway", None, BytesIO(b""))

    def read(self) -> bytes:  # type: ignore[override]
        raise OSError("corpo inacessível")

from apiclima.clima import (
    FORECAST_URL,
    GEOCODING_URL,
    _get_json,
    clima_atual_por_cidade,
)


def _geo_result(
    *,
    name: str = "London",
    country: str = "United Kingdom",
    latitude: float = 51.5074,
    longitude: float = -0.1278,
) -> dict:
    return {
        "results": [
            {
                "name": name,
                "country": country,
                "latitude": latitude,
                "longitude": longitude,
            }
        ]
    }


def _forecast_result() -> dict:
    return {
        "current": {
            "time": "2026-03-28T12:00",
            "temperature_2m": 14.2,
            "weather_code": 0,
        },
        "current_units": {"temperature_2m": "°C"},
    }


class TestClimaAtualPorCidade(unittest.TestCase):
    """clima_atual_por_cidade com _get_json simulado."""

    @patch("apiclima.clima._get_json")
    def test_sucesso_estrutura_e_primeiro_resultado(self, mock_get_json: MagicMock) -> None:
        mock_get_json.side_effect = [_geo_result(), _forecast_result()]

        out = clima_atual_por_cidade("London")

        self.assertEqual(mock_get_json.call_count, 2)
        self.assertEqual(out["local"]["nome"], "London")
        self.assertEqual(out["local"]["pais"], "United Kingdom")
        self.assertEqual(out["local"]["latitude"], 51.5074)
        self.assertEqual(out["local"]["longitude"], -0.1278)
        self.assertEqual(out["atual"]["temperature_2m"], 14.2)
        self.assertEqual(out["unidades"]["temperature_2m"], "°C")

        args1 = mock_get_json.call_args_list[1][0]
        self.assertEqual(args1[0], FORECAST_URL)
        self.assertEqual(args1[1]["latitude"], 51.5074)
        self.assertEqual(args1[1]["longitude"], -0.1278)
        self.assertEqual(args1[1]["timezone"], "auto")
        self.assertIn("temperature_2m", args1[1]["current"])

    @patch("apiclima.clima._get_json")
    def test_nome_com_espacos_usa_strip(self, mock_get_json: MagicMock) -> None:
        mock_get_json.side_effect = [_geo_result(name="São Paulo", latitude=-23.55, longitude=-46.63), _forecast_result()]

        clima_atual_por_cidade("  São Paulo  ")

        geo_call = mock_get_json.call_args_list[0][0]
        self.assertEqual(geo_call[0], GEOCODING_URL)
        self.assertEqual(geo_call[1]["name"], "São Paulo")

    @patch("apiclima.clima._get_json")
    def test_cidade_nao_encontrada(self, mock_get_json: MagicMock) -> None:
        mock_get_json.return_value = {"results": []}

        with self.assertRaises(LookupError) as ctx:
            clima_atual_por_cidade("CidadeInexistenteXYZ")

        self.assertIn("CidadeInexistenteXYZ", str(ctx.exception))
        mock_get_json.assert_called_once()

    @patch("apiclima.clima._get_json")
    def test_results_ausente_como_vazio(self, mock_get_json: MagicMock) -> None:
        mock_get_json.return_value = {}

        with self.assertRaises(LookupError):
            clima_atual_por_cidade("Xyz")

    @patch("apiclima.clima._get_json")
    def test_country_code_maiusculas(self, mock_get_json: MagicMock) -> None:
        mock_get_json.side_effect = [_geo_result(), _forecast_result()]

        clima_atual_por_cidade("London", country_code="br")

        params = mock_get_json.call_args_list[0][0][1]
        self.assertEqual(params["countryCode"], "BR")

    @patch("apiclima.clima._get_json")
    def test_language_repassada(self, mock_get_json: MagicMock) -> None:
        mock_get_json.side_effect = [_geo_result(), _forecast_result()]

        clima_atual_por_cidade("London", language="en")

        params = mock_get_json.call_args_list[0][0][1]
        self.assertEqual(params["language"], "en")

    @patch("apiclima.clima._get_json")
    def test_local_sem_name_e_country_opcionais(self, mock_get_json: MagicMock) -> None:
        mock_get_json.side_effect = [
            {"results": [{"latitude": 1.0, "longitude": 2.0}]},
            _forecast_result(),
        ]

        out = clima_atual_por_cidade("Algum")

        self.assertIsNone(out["local"]["nome"])
        self.assertIsNone(out["local"]["pais"])
        self.assertEqual(out["local"]["latitude"], 1.0)
        self.assertEqual(out["local"]["longitude"], 2.0)

    @patch("apiclima.clima._get_json")
    def test_nome_exatamente_dois_caracteres_aceito(self, mock_get_json: MagicMock) -> None:
        mock_get_json.side_effect = [
            _geo_result(name="Xi", country="China", latitude=34.8, longitude=108.9),
            _forecast_result(),
        ]

        out = clima_atual_por_cidade("Xi")

        self.assertEqual(mock_get_json.call_args_list[0][0][1]["name"], "Xi")
        self.assertEqual(out["local"]["nome"], "Xi")

    @patch("apiclima.clima._get_json")
    def test_unicode_acentos_e_caracteres_nao_latinos(self, mock_get_json: MagicMock) -> None:
        mock_get_json.side_effect = [
            _geo_result(name="München", country="Deutschland", latitude=48.14, longitude=11.58),
            _forecast_result(),
        ]

        clima_atual_por_cidade("München")

        self.assertEqual(mock_get_json.call_args_list[0][0][1]["name"], "München")

    @patch("apiclima.clima._get_json")
    def test_varios_resultados_usa_somente_primeiro(self, mock_get_json: MagicMock) -> None:
        mock_get_json.side_effect = [
            {
                "results": [
                    {"name": "Springfield", "country": "USA", "latitude": 39.8, "longitude": -89.6},
                    {"name": "Springfield", "country": "USA", "latitude": 42.1, "longitude": -72.5},
                ]
            },
            _forecast_result(),
        ]

        clima_atual_por_cidade("Springfield")

        fc_params = mock_get_json.call_args_list[1][0][1]
        self.assertEqual(fc_params["latitude"], 39.8)
        self.assertEqual(fc_params["longitude"], -89.6)

    @patch("apiclima.clima._get_json")
    def test_geocoding_sem_latitude_lookup_error(self, mock_get_json: MagicMock) -> None:
        mock_get_json.return_value = {"results": [{"longitude": 0.0}]}

        with self.assertRaises(LookupError) as ctx:
            clima_atual_por_cidade("Ab")

        self.assertIn("coordenadas", str(ctx.exception).lower())

    @patch("apiclima.clima._get_json")
    def test_geocoding_sem_longitude_lookup_error(self, mock_get_json: MagicMock) -> None:
        mock_get_json.return_value = {"results": [{"latitude": 0.0}]}

        with self.assertRaises(LookupError):
            clima_atual_por_cidade("Ab")

    @patch("apiclima.clima._get_json")
    def test_geocoding_latitude_nula_lookup_error(self, mock_get_json: MagicMock) -> None:
        mock_get_json.return_value = {"results": [{"latitude": None, "longitude": 1.0}]}

        with self.assertRaises(LookupError):
            clima_atual_por_cidade("Ab")

    @patch("apiclima.clima._get_json")
    def test_previsao_sem_current_nem_unidades(self, mock_get_json: MagicMock) -> None:
        mock_get_json.side_effect = [_geo_result(), {}]

        out = clima_atual_por_cidade("London")

        self.assertIsNone(out["atual"])
        self.assertIsNone(out["unidades"])

    @patch("apiclima.clima._get_json")
    def test_country_code_so_espacos_nao_enviado(self, mock_get_json: MagicMock) -> None:
        mock_get_json.side_effect = [_geo_result(), _forecast_result()]

        clima_atual_por_cidade("London", country_code="   ")

        params = mock_get_json.call_args_list[0][0][1]
        self.assertNotIn("countryCode", params)


class TestValidacaoNome(unittest.TestCase):
    def test_nome_vazio(self) -> None:
        with self.assertRaises(ValueError):
            clima_atual_por_cidade("")

    def test_somente_espacos(self) -> None:
        with self.assertRaises(ValueError):
            clima_atual_por_cidade("   ")

    def test_um_caractere(self) -> None:
        with self.assertRaises(ValueError):
            clima_atual_por_cidade("A")


class TestGetJsonRede(unittest.TestCase):
    """_get_json com urlopen simulado."""

    @patch("apiclima.clima.urlopen")
    def test_http_error_envolve_runtime_error_com_codigo(self, mock_urlopen: MagicMock) -> None:
        err = HTTPError(
            "https://example.com",
            503,
            "Service Unavailable",
            None,
            BytesIO(b'{"error":"busy"}'),
        )
        mock_urlopen.side_effect = err

        with self.assertRaises(RuntimeError) as ctx:
            _get_json(GEOCODING_URL, {"name": "x", "count": 1, "language": "pt"})

        self.assertIn("503", str(ctx.exception))
        self.assertIn("busy", str(ctx.exception))

    @patch("apiclima.clima.urlopen")
    def test_url_error_envolve_runtime_error(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = URLError("timed out")

        with self.assertRaises(RuntimeError) as ctx:
            _get_json(FORECAST_URL, {"latitude": 0, "longitude": 0})

        self.assertIn("rede", str(ctx.exception).lower())

    @patch("apiclima.clima.urlopen")
    def test_corpo_invalido_jsondecodeerror(self, mock_urlopen: MagicMock) -> None:
        cm = MagicMock()
        cm.read.return_value = b"not json {"
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = cm

        with self.assertRaises(json.JSONDecodeError):
            _get_json(GEOCODING_URL, {"name": "ok", "count": 1, "language": "pt"})

    @patch("apiclima.clima.urlopen")
    def test_corpo_vazio_jsondecodeerror(self, mock_urlopen: MagicMock) -> None:
        cm = MagicMock()
        cm.read.return_value = b""
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = cm

        with self.assertRaises(json.JSONDecodeError):
            _get_json(GEOCODING_URL, {"name": "ok", "count": 1, "language": "pt"})

    @patch("apiclima.clima.urlopen")
    def test_http_error_leitura_corpo_falha_usa_str_erro(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = _HTTPErrorCorpoIlegivel()

        with self.assertRaises(RuntimeError) as ctx:
            _get_json(FORECAST_URL, {"latitude": 0, "longitude": 0})

        self.assertIn("502", str(ctx.exception))

    @patch("apiclima.clima.urlopen")
    def test_url_error_timeout_envolve_runtime_error(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = URLError(TimeoutError("tempo esgotado"))

        with self.assertRaises(RuntimeError) as ctx:
            _get_json(FORECAST_URL, {"latitude": 0, "longitude": 0})

        self.assertIn("rede", str(ctx.exception).lower())


@unittest.skipUnless(
    os.environ.get("RUN_OPEN_METEO_INTEGRATION") == "1",
    "defina RUN_OPEN_METEO_INTEGRATION=1 para testes ao vivo com a Open-Meteo",
)
class TestIntegracaoOpenMeteo(unittest.TestCase):
    def test_london_retorna_atual_e_unidades(self) -> None:
        out = clima_atual_por_cidade("London", language="en")

        self.assertIn("atual", out)
        self.assertIn("unidades", out)
        self.assertIn("local", out)
        self.assertIsNotNone(out["atual"])
        self.assertIn("temperature_2m", out["atual"])


if __name__ == "__main__":
    unittest.main()

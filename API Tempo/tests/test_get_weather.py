"""Casos de teste para get_weather (testes.depurar.py)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEPURAR_PATH = PROJECT_ROOT / "testes.depurar.py"
_DEPURAR_MOD_NAME = "testes_depurar_mod"


def _load_get_weather():
    spec = importlib.util.spec_from_file_location(_DEPURAR_MOD_NAME, _DEPURAR_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_DEPURAR_MOD_NAME] = mod
    spec.loader.exec_module(mod)
    return mod.get_weather


get_weather = _load_get_weather()


def _response_ok(json_data: dict, *, text: str | None = None) -> MagicMock:
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json.return_value = json_data
    r.text = text if text is not None else json.dumps(json_data)
    return r


class TestGetWeatherMocked(unittest.TestCase):
    """Testes rápidos com API simulada (não usam rede)."""

    @patch(f"{_DEPURAR_MOD_NAME}.requests.get")
    def test_sucesso_estrutura_e_previsao(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = [
            _response_ok(
                {
                    "results": [
                        {
                            "name": "Tóquio",
                            "country": "Japão",
                            "latitude": 35.6895,
                            "longitude": 139.69171,
                        }
                    ]
                }
            ),
            _response_ok(
                {
                    "latitude": 35.7,
                    "longitude": 139.6875,
                    "current_weather": {
                        "temperature": 12.5,
                        "windspeed": 3.9,
                        "weathercode": 0,
                    },
                }
            ),
        ]

        out = get_weather("Tokyo")

        self.assertIn("local", out)
        self.assertIn("previsao", out)
        self.assertEqual(out["local"]["latitude"], 35.6895)
        self.assertEqual(out["local"]["longitude"], 139.69171)
        self.assertIn("current_weather", out["previsao"])
        self.assertEqual(out["previsao"]["current_weather"]["temperature"], 12.5)

        self.assertEqual(mock_get.call_count, 2)
        args0, kwargs0 = mock_get.call_args_list[0]
        self.assertIn("geocoding-api.open-meteo.com", args0[0])
        self.assertEqual(kwargs0["params"]["name"], "Tokyo")

        args1, kwargs1 = mock_get.call_args_list[1]
        self.assertIn("api.open-meteo.com", args1[0])
        self.assertEqual(kwargs1["params"]["latitude"], 35.6895)
        self.assertEqual(kwargs1["params"]["longitude"], 139.69171)
        self.assertEqual(kwargs1["params"]["current_weather"], "true")

    @patch(f"{_DEPURAR_MOD_NAME}.requests.get")
    def test_cidade_nao_encontrada_lookup_error(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _response_ok({"results": []})

        with self.assertRaises(LookupError) as ctx:
            get_weather("CidadeInexistenteXYZ123")

        self.assertIn("não encontrada", str(ctx.exception))
        mock_get.assert_called_once()

    @patch(f"{_DEPURAR_MOD_NAME}.requests.get")
    def test_resposta_previsao_vazia_runtime_error(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = [
            _response_ok(
                {
                    "results": [
                        {
                            "name": "X",
                            "country": "Y",
                            "latitude": 0.0,
                            "longitude": 0.0,
                        }
                    ]
                }
            ),
            _response_ok({}, text="   "),
        ]

        with self.assertRaises(RuntimeError) as ctx:
            get_weather("X")

        self.assertIn("vazia", str(ctx.exception))


@unittest.skipUnless(
    os.environ.get("RUN_OPEN_METEO_INTEGRATION") == "1",
    "defina RUN_OPEN_METEO_INTEGRATION=1 para testes ao vivo com a Open-Meteo",
)
class TestGetWeatherIntegracao(unittest.TestCase):
    """Chamadas reais à API (rede necessária)."""

    def test_tokyo_retorna_clima_atual(self) -> None:
        out = get_weather("Tokyo")
        self.assertIn("current_weather", out["previsao"])
        cw = out["previsao"]["current_weather"]
        self.assertIn("temperature", cw)
        self.assertIsInstance(cw["temperature"], (int, float))

    def test_cidade_inexistente(self) -> None:
        with self.assertRaises(LookupError):
            get_weather("ZZZNoSuchCityOpenMeteo999")


if __name__ == "__main__":
    unittest.main()

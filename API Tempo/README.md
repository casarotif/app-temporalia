# API Tempo

Aplicação em Python para **previsão do tempo** a partir do **nome de uma cidade**. O projeto consulta a [Open-Meteo](https://open-meteo.com/) (geocodificação + previsão) e devolve temperatura à superfície, humidade relativa, velocidade e direção do vento, entre outros campos atuais, com **tratamento de erros** para entradas inválidas, cidades inexistentes e falhas de rede. Os dados são da Open-Meteo; ver termos de uso no site oficial.

> **Nota:** O módulo principal devolve dados estruturados em memória; podes **gravar as respostas num ficheiro** (JSON, log, etc.) na camada da tua aplicação ou CLI — ver [Guia de uso](#guia-de-uso) e [Melhorias futuras](#melhorias-futuras).

> **Privacidade (cache):** se usares a função com SWR/cache, as respostas podem ser persistidas em disco por padrão (por utilizador). Em máquinas partilhadas, considera desativar cache ou escolher um `cache_dir` apropriado.

---

## Visão geral

1. O utilizador (ou outro código) indica o nome da cidade.
2. A **API de geocodificação** Open-Meteo resolve o nome para coordenadas (primeiro resultado).
3. A **API de previsão** devolve o bloco `current` com variáveis meteorológicas pedidas (temperatura, humidade, vento, código meteorológico, etc.).
4. Erros como cidade desconhecida, nome demasiado curto, coordenadas inválidas na resposta ou problemas HTTP/rede são convertidos em exceções claras (`LookupError`, `ValueError`, `RuntimeError`).

O núcleo do projeto está no pacote **`apiclima`**, sem dependências obrigatórias além da biblioteca padrão do Python.

---

## Funcionalidades

- Busca por **nome de cidade** com normalização (`strip`) e validação de comprimento mínimo.
- Parâmetros opcionais de geocodificação: **`language`** e **`countryCode`** (código de país ISO).
- Dados atuais incluindo **temperatura** (`temperature_2m`), **humidade** (`relative_humidity_2m`), **vento** (`wind_speed_10m`, `wind_direction_10m`), sensação térmica, precipitação e código meteorológico.
- **Tratamento de erros**: cidade não encontrada, coordenadas ausentes ou inválidas, erros HTTP e falhas de rede na chamada à API.
- **Testes automatizados** (`unittest`) com mocks, mais teste de integração opcional com a API real.

---

## Requisitos

| Item | Detalhe |
|------|---------|
| **Python** | 3.9 ou superior (recomendado 3.10+) |
| **Dependências do `apiclima`** | Apenas biblioteca padrão (`urllib`, `json`, etc.) |
| **Rede** | Acesso HTTPS às APIs `geocoding-api.open-meteo.com` e `api.open-meteo.com` |
| **Testes** | `unittest` incluído no Python; execução opcional com variável de ambiente para integração |

Scripts em `tests/` que usam `requests` são exemplos ou testes antigos e exigem `pip install requests` se quiseres executá-los.

---

## Instalação

1. Clona ou copia este repositório para a tua máquina.

2. (Opcional) Cria e ativa um ambiente virtual:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. Garante que a pasta do projeto está no **PYTHONPATH** ao importar o pacote, ou executa os comandos a partir da raiz do repositório:

   ```bash
   cd "caminho/para/API Tempo"
   ```

Não é obrigatório `pip install` para usar apenas `apiclima`; para testes de integração ao vivo, não é necessário pacote extra.

Se fores executar o servidor local (endpoint HTTP + UI), instala dependências:

```bash
python -m pip install -r requirements.txt
```

---

## Guia de uso

### Como módulo Python

```python
from apiclima.clima import clima_atual_por_cidade

try:
    dados = clima_atual_por_cidade("Lisboa", language="pt")
    print(dados["local"])
    print(dados["atual"])
except LookupError as e:
    print("Cidade ou coordenadas inválidas:", e)
except ValueError as e:
    print("Entrada inválida:", e)
except RuntimeError as e:
    print("Erro da API ou rede:", e)
```

- **`language`**: idioma dos nomes na geocodificação (por defeito `"pt"`).
- **`country_code`**: por exemplo `"PT"` para restringir a país (opcional).

### Executar testes

Na raiz do projeto:

```bash
python -m unittest apiclima.test_clima -v
```

Teste opcional contra a API real (requer rede):

```bash
set RUN_OPEN_METEO_INTEGRATION=1
python -m unittest apiclima.test_clima.TestIntegracaoOpenMeteo -v
```

(PowerShell: `$env:RUN_OPEN_METEO_INTEGRATION="1"`)

### Gravar respostas num ficheiro

O módulo devolve um `dict` serializável em JSON. Exemplo mínimo:

```python
import json
from pathlib import Path
from apiclima.clima import clima_atual_por_cidade

out = clima_atual_por_cidade("Porto")
Path("ultima_consulta.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
```

---

## Exemplo de resultado

Estrutura típica devolvida por `clima_atual_por_cidade` (valores ilustrativos):

```json
{
  "local": {
    "nome": "Lisboa",
    "pais": "Portugal",
    "latitude": 38.71667,
    "longitude": -9.13333
  },
  "atual": {
    "time": "2026-03-28T12:00",
    "temperature_2m": 18.4,
    "relative_humidity_2m": 65,
    "apparent_temperature": 17.9,
    "precipitation": 0.0,
    "weather_code": 2,
    "wind_speed_10m": 12.3,
    "wind_direction_10m": 280
  },
  "unidades": {
    "temperature_2m": "°C",
    "relative_humidity_2m": "%",
    "wind_speed_10m": "km/h"
  }
}
```

Os campos exatos em `atual` e `unidades` seguem a documentação da Open-Meteo e podem variar conforme a API.

---

## Melhorias futuras

- Registo persistente **integrado** (logging configurável, rotação de ficheiros ou base de dados).
- Interface de linha de comando (CLI) com argumentos (`cidade`, `--pais`, `--json`).
- Ficheiro `requirements.txt` / `pyproject.toml` para dependências opcionais (`requests`, ferramentas de lint).
- Suporte a **escolha entre vários resultados** de geocodificação quando existem homónimos.
- Cache de coordenadas por cidade para reduzir chamadas repetidas.

---

## Licença

Este projeto usa a licença **MIT** (ver `LICENSE`).

### Terceiros e termos de uso

- **Open‑Meteo**: o projeto consome endpoints públicos da Open‑Meteo. Confere os **termos de uso**/limites diretamente no site da Open‑Meteo antes de usar em produção.

Contribuições (*pull requests*) são bem-vindas: confirma que `python -m unittest apiclima.test_clima -v` continua a passar antes de submeter.

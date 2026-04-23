import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def get_weather(city: str) -> dict:
    geo = requests.get(
        GEOCODING_URL,
        params={"name": city, "count": 1, "language": "pt"},
        timeout=10,
    )
    geo.raise_for_status()
    data_geo = geo.json()
    results = data_geo.get("results") or []
    if not results:
        raise LookupError(f'Cidade não encontrada: "{city}"')

    loc = results[0]
    lat, lon = loc["latitude"], loc["longitude"]

    forecast = requests.get(
        FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true",
            "timezone": "auto",
        },
        timeout=10,
    )
    forecast.raise_for_status()
    if not forecast.text.strip():
        raise RuntimeError("Resposta vazia da API de previsão.")

    return {
        "local": {
            "nome": loc.get("name"),
            "pais": loc.get("country"),
            "latitude": lat,
            "longitude": lon,
        },
        "previsao": forecast.json(),
    }


if __name__ == "__main__":
    print(get_weather("Tokyo"))

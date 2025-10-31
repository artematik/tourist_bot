import logging
import json
import math
from typing import Any, Dict, List, Optional, Tuple

import httpx
from config import settings

logger = logging.getLogger(__name__)

def _haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Расстояние между координатами (lat, lon) в км."""
    R = 6371.0
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(h))

SPEEDS_KMH = {
    "walk": 4.5,
    "bike": 15.0,
    "car": 30.0,
}

class IonetRouteService:
    """
    Генерация маршрута через IO.net API (или fallback).
    """

    async def optimize_route(
        self,
        start: Dict[str, Any],
        pois: List[Dict[str, Any]],
        time_budget_min: float,
        transport: str,
        interests: str,
    ) -> Optional[Dict[str, Any]]:
        if not pois:
            logger.warning("⚠️ Пустой список POI передан в Ionet — возвращаем fallback.")
            return None

        api_key = settings.IONET_API_KEY
        base_url = "https://api.intelligence.io.solutions/api/v1"
        model_name = getattr(settings, "IONET_MODEL", None) or "mistralai/Mistral-Large-Instruct-2411"

        try:
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "You are a route planning assistant."},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "task": "build_city_route",
                                "start": start,  # {name?, lat, lon}
                                "transport": transport,
                                "time_budget_min": time_budget_min,
                                "interests": interests,
                                "pois": pois,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                "temperature": 0.2,
            }

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{base_url}/chat/completions", headers=headers, json=payload
                )
                # если ошибка — залогируем тело и выбросим исключение, чтобы пойти в fallback
                if resp.is_error:
                    err_text = resp.text
                    logger.error("Ionet HTTP %s. Body: %s", resp.status_code, err_text)
                    raise RuntimeError(f"Ionet HTTP {resp.status_code}")
                data = resp.json()

            # Безопасное логирование содержимого
            raw = (
                data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
            )
            preview = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
            logger.info("📦 Ответ Ionet (обрезан): %s...", preview[:250])

            # Приводим ответ к dict
            if isinstance(raw, str):
                try:
                    route_json = json.loads(raw)
                except Exception:
                    route_json = {}
            elif isinstance(raw, dict):
                route_json = raw
            else:
                route_json = {}

            distance_km = float(route_json.get("distance_km") or 0.0)
            duration_min = float(route_json.get("duration_min") or 0.0)
            steps = route_json.get("steps") or []


            if (distance_km <= 0 or duration_min <= 0) and steps:
                coords: List[Tuple[float, float]] = []
                if "lat" in start and "lon" in start:
                    coords.append((start["lat"], start["lon"]))
                for s in steps:
                    if "lat" in s and "lon" in s:
                        coords.append((s["lat"], s["lon"]))
                if len(coords) >= 2:
                    distance_km = sum(
                        _haversine_km(coords[i], coords[i + 1])
                        for i in range(len(coords) - 1)
                    )
                if distance_km > 0:
                    speed = SPEEDS_KMH.get(transport, SPEEDS_KMH["walk"])
                    duration_min = round(distance_km / speed * 60)

            if steps or (distance_km > 0 and duration_min > 0):
                return {
                    "transport": transport,
                    "distance_km": round(distance_km, 1),
                    "duration_min": int(max(1, duration_min)),
                    "steps": steps,
                    "meta": {"source": "ionet"},
                }

        except Exception as e:
            logger.error("❌ Ошибка при обращении к Ionet API: %s", e, exc_info=True)

        # --- Fallback: простой маршрут NN + оценка времени
        try:
            coords: List[Tuple[float, float]] = []
            if "lat" in start and "lon" in start:
                coords.append((start["lat"], start["lon"]))
            for p in pois:
                if "lat" in p and "lon" in p:
                    coords.append((p["lat"], p["lon"]))

            if len(coords) < 2:
                return None

            # Жадный NN от старта
            unvisited = coords[1:]
            route = [coords[0]]
            while unvisited:
                last = route[-1]
                j = min(range(len(unvisited)), key=lambda k: _haversine_km(last, unvisited[k]))
                route.append(unvisited.pop(j))

            distance_km = sum(
                _haversine_km(route[i], route[i + 1]) for i in range(len(route) - 1)
            )
            speed = SPEEDS_KMH.get(transport, SPEEDS_KMH["walk"])
            duration_min = round(distance_km / speed * 60)

            steps = [{"lat": pt[0], "lon": pt[1]} for pt in route[1:]]

            return {
                "transport": transport,
                "distance_km": round(distance_km, 1),
                "duration_min": int(max(1, duration_min)),
                "steps": steps,
                "meta": {"source": "fallback"},
            }
        except Exception as e:
            logger.error("❌ Fallback-маршрут не собран: %s", e, exc_info=True)
            return None

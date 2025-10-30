# services/ai_service.py
import asyncio
import logging
import math
import random
from typing import Dict, Any, Optional, List, Tuple

from services.ionet_route_service import IonetRouteService
from services.places_provider import fetch_pois_nearby
from services.poi_enricher import PoiEnricher

logger = logging.getLogger(__name__)


def _haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    R = 6371.0
    la1, lo1 = map(math.radians, a)
    la2, lo2 = map(math.radians, b)
    dlat = la2 - la1
    dlon = lo2 - lo1
    h = math.sin(dlat / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


_SPEEDS_KMH = {
    "walk": 4.5,
    "bike": 14.0,
    "scooter": 18.0,
    "car": 40.0,
    "transit": 25.0,
}


def _norm_transport(t: str) -> str:
    t = (t or "walk").lower()
    if "car" in t or "авто" in t or "маш" in t:
        return "car"
    if "bike" in t or "вел" in t or "самокат" in t:
        return "bike"
    if "transit" in t or "обще" in t or "bus" in t or "метро" in t:
        return "transit"
    return "walk"


def _looks_generic_name(name: str) -> bool:
    n = (name or "").strip().lower()
    if not n or n in {"russia", "россия"}:
        return True
    if n.endswith(" russia") or n.endswith(" россия"):
        return True
    if n in {"nizhny novgorod", "нижний новгород"}:
        return True
    # частые generic: просто "Russia" / "Nizhny Novgorod, Russia"
    if ", russia" in n or "нижегородская область" in n:
        return True
    return False


def _filter_generic_pois(pois: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Убираем явные generic-POI (узлы с именем 'Nizhny Novgorod, Russia' и т.п.),
    чтобы маршрут не включал абстрактные "районы".
    """
    cleaned = []
    for p in pois:
        name = (p.get("name") or p.get("title") or p.get("label") or "").strip()
        if _looks_generic_name(name):
            continue
        cleaned.append(p)
    # если всё выкинули — вернём исходное, чтобы не оголить маршрут
    return cleaned or pois


def _pick_pois_with_seed(pois: List[Dict[str, Any]], seed: int, max_stops: int) -> List[Dict[str, Any]]:
    """Детерминированно перемешиваем и берём верхушку."""
    rnd = random.Random(seed)
    shuffled = pois[:]  # не мутируем оригинал
    rnd.shuffle(shuffled)
    return shuffled[:max_stops]


def _nn_order(start: Tuple[float, float], pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Простой жадный NN-порядок обхода точек от старта."""
    if not pts:
        return []
    unvisited = pts[:]
    route = []
    cur = start
    while unvisited:
        j = min(range(len(unvisited)), key=lambda k: _haversine_km(cur, unvisited[k]))
        nxt = unvisited.pop(j)
        route.append(nxt)
        cur = nxt
    return route


def _build_stops_and_summary(
    *,
    start_label: str,
    start_lat: float,
    start_lon: float,
    transport: str,
    picked_pois: List[Dict[str, Any]],
    target_minutes: int,
) -> Dict[str, Any]:
    """
    Собираем итоговую структуру:
    - stops[]: name, description, lat, lon, leg_min, stay_min
    - summary: transport, start_lat/lon/label, total_km, eta_min ~= target_minutes
    """
    speed = _SPEEDS_KMH.get(transport, 4.5)
    start_xy = (start_lat, start_lon)

    pts_xy: List[Tuple[float, float]] = []
    for p in picked_pois:
        if "lat" in p and "lon" in p:
            pts_xy.append((float(p["lat"]), float(p["lon"])))
    ordered_xy = _nn_order(start_xy, pts_xy)

    # индекс для вытягивания названий/описаний по координатам
    by_xy = {(float(p["lat"]), float(p["lon"])): p for p in picked_pois if "lat" in p and "lon" in p}

    stops: List[Dict[str, Any]] = []
    prev = start_xy
    total_km = 0.0
    travel_min = 0

    for i, xy in enumerate(ordered_xy, 1):
        p = by_xy.get(xy, {})
        name = p.get("name") or p.get("title") or p.get("label") or f"Точка {i}"
        desc = p.get("description") or p.get("addr") or p.get("address") or p.get("city") or ""
        dist = _haversine_km(prev, xy)
        leg_min = int(round(dist / max(speed, 0.1) * 60))
        total_km += dist
        travel_min += leg_min
        stops.append(
            {
                "name": name,
                "description": desc,
                "lat": xy[0],
                "lon": xy[1],
                "leg_min": leg_min,
                "stay_min": 0,  # заполним ниже
            }
        )
        prev = xy

    # Базовые стоянки и довыравнивание под целевое время
    planned = max(1, int(target_minutes))
    base_stay = 10  # базовые минуты на каждой точке
    base_total = base_stay * len(stops)
    eta_now = travel_min + base_total
    extra = max(0, planned - eta_now)

    per_stop = (extra // len(stops)) if stops else 0
    rem = (extra % len(stops)) if stops else 0
    for idx, s in enumerate(stops):
        s["stay_min"] = base_stay + per_stop + (1 if idx < rem else 0)

    eta_final = travel_min + sum(s["stay_min"] for s in stops)

    summary = {
        "transport": transport,
        "start_lat": start_lat,
        "start_lon": start_lon,
        "start_label": start_label or "Старт",
        "total_km": round(total_km, 1),
        "eta_min": int(eta_final),
    }
    return {"stops": stops, "summary": summary}


class AIService:
    def __init__(self):
        self.ionet_service = IonetRouteService()
        self.poi_enricher = PoiEnricher()

    async def generate_route(
        self,
        lat: float,
        lon: float,
        interests: str,
        time_hours: float,
        transport: str,
        location: Optional[str] = None,
        diversity_seed: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:

        tmode = _norm_transport(transport)
        total_minutes = int(time_hours * 60)

        logger.info(
            f"🧭 Генерация маршрута через Ionet API: {interests}, {time_hours:.1f}ч, "
            f"{tmode}, старт={location or 'геопозиция'}"
        )

        # Радиус под скорость
        speed_kmh = _SPEEDS_KMH.get(tmode, 4.5)
        max_distance_km = speed_kmh * (time_hours * 0.6)
        search_radius_m = int(max(800, min(max_distance_km * 1000, 15000)))
        logger.info(f"🔍 Радиус поиска POI: {search_radius_m} м (скорость={speed_kmh} км/ч)")

        # 1) POI из провайдера
        try:
            pois = fetch_pois_nearby(lat, lon, interests, search_radius_m)
        except Exception as e:
            logger.warning(f"⚠️ Overpass не ответил или вернул ошибку: {e}")
            pois = []

        if not pois:
            # Вернём простую прогулку по месту старта, чтобы форматтер не падал
            logger.warning("⚠️ Overpass не вернул ни одной точки, используем один центр как fallback.")
            result = {
                "stops": [
                    {
                        "name": location or "Стартовая точка",
                        "description": "Прогулка рядом с точкой старта.",
                        "lat": lat,
                        "lon": lon,
                        "leg_min": 0,
                        "stay_min": max(1, total_minutes - 0),
                    }
                ],
                "summary": {
                    "transport": tmode,
                    "start_lat": lat,
                    "start_lon": lon,
                    "start_label": location or "Старт",
                    "total_km": 0.0,
                    "eta_min": total_minutes,
                },
                "meta": {"source": "fallback", "reason": "No POI"},
            }
            logger.info("✅ Маршрут готов (источник: %s)", result.get("meta", {}).get("source"))
            return result

        # 1.1) выкинем generic-POI (город/страна)
        pois = _filter_generic_pois(pois)

        # 2) Детерминированно выбираем подмножество POI по seed → новые маршруты при "Сгенерировать ещё"
        seed = (diversity_seed or 0) ^ (hash(interests) & 0x7FFFFFFF)
        max_stops = max(3, min(12, 2 + int(time_hours * 2)))  # 2 точки на час, но минимум 3 и не >12
        picked = _pick_pois_with_seed(pois, seed=seed, max_stops=max_stops)

        # 3) Пытаемся через Ionet. Он может вернуть steps без времени — рассчитаем.
        start = {"lat": lat, "lon": lon, "name": location or "Стартовая точка"}

        ionet_result: Optional[Dict[str, Any]] = None
        try:
            ionet_result = await asyncio.wait_for(
                self.ionet_service.optimize_route(
                    start=start,
                    pois=picked,  # важный момент: передаём уже "перетасованные" точки
                    time_budget_min=total_minutes,
                    transport=tmode,
                    interests=interests,
                ),
                timeout=90,
            )
        except asyncio.TimeoutError:
            logger.error("⏱️ Ionet API превысил время ожидания (timeout).")
        except Exception as e:
            logger.exception(f"❌ Ошибка Ionet API: {e}")

        # 4) Если Ionet дал годный ответ со steps — конвертируем steps → stops и выравниваем время
        if ionet_result and isinstance(ionet_result, dict) and ionet_result.get("steps"):
            steps = ionet_result.get("steps", [])
            # Приведём к виду picked для унификации (подтянем name/description из picked по координатам)
            by_xy = {(float(p["lat"]), float(p["lon"])): p for p in picked if "lat" in p and "lon" in p}
            enriched_steps: List[Dict[str, Any]] = []
            for i, s in enumerate(steps, 1):
                lat_s = float(s.get("lat"))
                lon_s = float(s.get("lon"))
                base = by_xy.get((lat_s, lon_s), {})
                name = s.get("name") or base.get("name") or base.get("title") or f"Точка {i}"
                desc = s.get("description") or base.get("description") or base.get("addr") or ""
                # выбрасываем generic-названия прямо тут
                if _looks_generic_name(name):
                    continue
                enriched_steps.append(
                    {
                        "name": name,
                        "description": desc,
                        "lat": lat_s,
                        "lon": lon_s,
                        "leg_min": 0,   # рассчитаем ниже
                        "stay_min": 0,  # распределим ниже
                    }
                )

            result = _build_stops_and_summary(
                start_label=location or "Старт",
                start_lat=lat,
                start_lon=lon,
                transport=tmode,
                picked_pois=enriched_steps,
                target_minutes=total_minutes,
            )
            result.setdefault("meta", {})["source"] = "ionet"
        else:
            # 5) Fallback: полностью локально строим маршрут (NN) из picked и выравниваем время под запрос
            result = _build_stops_and_summary(
                start_label=location or "Старт",
                start_lat=lat,
                start_lon=lon,
                transport=tmode,
                picked_pois=picked,
                target_minutes=total_minutes,
            )
            result.setdefault("meta", {})["source"] = "fallback"
            result["meta"]["reason"] = "Ionet empty/400/429"

        # ── Обогащаем descriptions там, где они «пустые»; кэш защитит от 429 на ре-генерациях
        try:
            result["stops"] = await self.poi_enricher.enrich_stops(
                result.get("stops", []),
                interests=interests,
                locale="ru",
            )
        except Exception as e:
            logger.warning("Не удалось обогатить описания POI: %s", e)

        logger.info("✅ Маршрут готов (источник: %s)", result.get("meta", {}).get("source"))
        return result


ai_service = AIService()

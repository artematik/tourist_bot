# services/geocoder.py
from __future__ import annotations

import asyncio
import logging
import ssl
from typing import Optional, Tuple

import certifi
import requests
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

logger = logging.getLogger(__name__)

# --- Настройки геокодера ---
USER_AGENT = "tourist_ai_bot/1.0 (Nizhny Novgorod)"
LANG = "ru"
TIMEOUT = 10

# Ограничиваем поиск Нижегородской областью (примерная bbox)
# west, south, east, north
NN_BBOX = (41.5, 54.0, 47.8, 58.8)
COUNTRYCODES = "ru"


def _ssl_ctx() -> ssl.SSLContext:
    """SSL-контекст с системными сертификатами (решает SSL: CERTIFICATE_VERIFY_FAILED на macOS)."""
    ctx = ssl.create_default_context(cafile=certifi.where())
    return ctx


def _nominatim() -> Nominatim:
    return Nominatim(user_agent=USER_AGENT, ssl_context=_ssl_ctx(), timeout=TIMEOUT)


def _short_display(addr: dict) -> str:
    """
    Делаем «короткий» адрес: улица, дом, район/город.
    addr — это address из ответа nominatim.
    """
    parts = []
    road = addr.get("road") or addr.get("pedestrian") or addr.get("footway") or addr.get("cycleway")
    house = addr.get("house_number")
    suburb = addr.get("neighbourhood") or addr.get("suburb") or addr.get("city_district")
    city = addr.get("city") or addr.get("town") or addr.get("village")
    attraction = addr.get("attraction") or addr.get("tourism") or addr.get("amenity") or addr.get("building")

    if attraction and not road:
        parts.append(attraction)
    if road:
        parts.append(road + (f", {house}" if house else ""))
    if suburb:
        parts.append(suburb)
    if city:
        parts.append(city)

    text = ", ".join(p for p in parts if p)
    return text or addr.get("display_name") or "Точка на карте"


def _forward_sync(query: str) -> Optional[Tuple[float, float, str]]:
    """Синхронный геокодинг (внутри выполнится с RateLimiter)."""
    geo = _nominatim()
    geocode = RateLimiter(geo.geocode, min_delay_seconds=1, max_retries=2, error_wait_seconds=1.5, swallow_exceptions=True)
    try:
        loc = geocode(
            query,
            country_codes=COUNTRYCODES,
            language=LANG,
            addressdetails=True,
            viewbox=((NN_BBOX[1], NN_BBOX[0]), (NN_BBOX[3], NN_BBOX[2])),  # (south, west) → (north, east)
            bounded=True,
            limit=1,
        )
        if loc:
            lat, lon = float(loc.latitude), float(loc.longitude)
            disp = _short_display(getattr(loc, "raw", {}).get("address", {}))
            return lat, lon, disp
    except Exception as e:
        logger.warning("Nominatim forward error: %s", e)

    # Фолбэк: прямой JSON-вызов Nominatim
    try:
        params = {
            "q": query,
            "format": "jsonv2",
            "limit": 1,
            "accept-language": LANG,
            "countrycodes": COUNTRYCODES,
            "viewbox": f"{NN_BBOX[0]},{NN_BBOX[3]},{NN_BBOX[2]},{NN_BBOX[1]}",
            "bounded": 1,
            "addressdetails": 1,
        }
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        if data:
            item = data[0]
            lat, lon = float(item["lat"]), float(item["lon"])
            disp = _short_display(item.get("address", {}))
            return lat, lon, disp
    except Exception as e:
        logger.warning("Nominatim JSON fallback error: %s", e)

    return None


def _reverse_sync(lat: float, lon: float) -> Optional[str]:
    """Синхронный реверс-геокодинг → короткий адрес."""
    geo = _nominatim()
    reverse = RateLimiter(geo.reverse, min_delay_seconds=1, max_retries=2, error_wait_seconds=1.5, swallow_exceptions=True)
    try:
        loc = reverse(
            (lat, lon),
            language=LANG,
            addressdetails=True,
            zoom=17,
        )
        if loc:
            return _short_display(getattr(loc, "raw", {}).get("address", {}))
    except Exception as e:
        logger.warning("Nominatim reverse error: %s", e)

    # Фолбэк: JSON
    try:
        params = {
            "lat": lat,
            "lon": lon,
            "format": "jsonv2",
            "accept-language": LANG,
            "addressdetails": 1,
            "zoom": 17,
        }
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        addr = data.get("address", {})
        return _short_display(addr) if addr else data.get("display_name")
    except Exception as e:
        logger.warning("Nominatim reverse JSON fallback error: %s", e)

    return None


async def forward_geocode(query: str) -> Optional[Tuple[float, float, str]]:
    """Асинхронная обёртка для геокодинга текста."""
    query = (query or "").strip()
    if not query:
        return None
    return await asyncio.to_thread(_forward_sync, query)


async def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """Асинхронная обёртка для реверс-геокодинга."""
    return await asyncio.to_thread(_reverse_sync, lat, lon)


class Geocoder:
    """
    Совместимый интерфейс с предыдущей версией.
    Используется из handlers/questionnaire.py.
    """

    @staticmethod
    async def get_coordinates(query: str) -> Optional[Tuple[float, float]]:
        """
        Возвращает (lat, lon) для введённого текста в пределах НО (bbox).
        """
        res = await forward_geocode(query)
        if res is None:
            return None
        lat, lon, _ = res
        return lat, lon

    @staticmethod
    async def get_address_from_coords(lat: float, lon: float) -> Optional[str]:
        """
        Возвращает «короткий» адрес по координатам.
        """
        return await reverse_geocode(lat, lon)

    @staticmethod
    def is_within_region(lat: float, lon: float) -> bool:
        """
        Простейшая проверка, что точка попадает в bbox Нижегородской области.
        """
        west, south, east, north = NN_BBOX
        return (south <= lat <= north) and (west <= lon <= east)

# services/places_provider.py
# services/places_provider.py
import requests
import logging
import time
from typing import List, Dict, Any, Optional
from config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.geoapify.com/v2/places"

# Ключевые категории для сопоставления интересов
CATEGORY_MAP = {
    "музей": "entertainment.museum",
    "музеи": "entertainment.museum",
    "арт": "entertainment.art_gallery",
    "галерея": "entertainment.art_gallery",
    "парки": "leisure.park",
    "кафе": "catering.cafe",
    "еда": "catering.restaurant",
    "ресторан": "catering.restaurant",
    "библиотека": "education.library",
    "книги": "shop.books",
    "достопримечательности": "tourism.sights",
    "панорама": "natural.viewpoint",
    "street_art": "entertainment.art_gallery",
}

def _map_interest_to_category(interests: str) -> str:
    for key, cat in CATEGORY_MAP.items():
        if key in interests.lower():
            return cat
    return "tourism.sights"

def fetch_pois_nearby(lat: float, lon: float, interests: str,
                      radius_m: int, max_results: int = 20) -> List[Dict[str, Any]]:
    """
    Получение POI через Geoapify Places API
    """
    category = _map_interest_to_category(interests)
    params = {
        "categories": category,
        "filter": f"circle:{lon},{lat},{radius_m}",
        "bias": f"proximity:{lon},{lat}",
        "limit": max_results,
        "apiKey": settings.GEOAPIFY_API_KEY,
    }

    logger.info(f"🌍 Geoapify запрос: категории={category}, радиус={radius_m}м, центр=({lat},{lon})")

    try:
        r = requests.get(BASE_URL, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        features = data.get("features", [])

        pois = []
        for f in features:
            prop = f.get("properties", {})
            geom = f.get("geometry", {})
            coords = geom.get("coordinates", [None, None])
            name = prop.get("name") or prop.get("formatted") or "Неизвестное место"

            pois.append({
                "name": name,
                "description": prop.get("address_line2", "") or prop.get("details", ""),
                "category": prop.get("categories", ["poi"])[0] if prop.get("categories") else "poi",
                "lat": coords[1],
                "lon": coords[0],
                "url": prop.get("website"),
            })

        logger.info(f"✅ Geoapify вернул {len(pois)} POI.")
        return pois

    except Exception as e:
        logger.error(f"❌ Ошибка Geoapify: {e}")
        return []
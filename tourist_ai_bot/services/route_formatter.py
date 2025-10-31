from typing import Dict, Any, List
from urllib.parse import quote_plus
import math
import datetime


# --- Форматирование времени и длительности ---
def _fmt_time_min(m: int) -> str:
    m = max(0, int(m))
    h = m // 60
    mm = m % 60
    if h and mm:
        return f"{h} ч {mm} мин"
    if h:
        return f"{h} ч"
    return f"{mm} мин"


def _fmt_hhmm(dt_str: str) -> str:
    """Безопасное форматирование ISO-даты в 'HH:MM'."""
    if not dt_str:
        return "—"
    try:
        dt = datetime.datetime.fromisoformat(dt_str)
        return dt.strftime("%H:%M")
    except Exception:
        return str(dt_str)


# --- Сопоставление режимов транспорта ---
def _mode_to_gmaps(transport: str) -> str:
    return {
        "walk": "walking",
        "bike": "bicycling",
        "scooter": "bicycling",
        "car": "driving",
        "transit": "transit",
    }.get(transport, "walking")


def _mode_to_yamaps(transport: str) -> str:
    return {
        "walk": "walking",
        "bike": "bicycle",
        "scooter": "bicycle",
        "car": "driving",
        "transit": "masstransit",
    }.get(transport, "walking")


# --- Ссылки на карты ---
def _map_link_point(lat: float, lon: float, provider: str = "google") -> str:
    if provider == "yandex":
        return f"https://yandex.ru/maps/?pt={lon},{lat}&z=16&l=map"
    return f"https://www.google.com/maps?q={lat},{lon}"


def _map_link_route(
    start_lat: float,
    start_lon: float,
    stops: List[Dict[str, Any]],
    provider: str = "google",
    mode: str = "walking",
) -> str:
    if not stops:
        return ""
    if provider == "google":
        origin = f"{start_lat},{start_lon}"
        dest = f"{stops[-1]['lat']},{stops[-1]['lon']}"
        waypoints = [f"{s['lat']},{s['lon']}" for s in stops[:-1]]
        wp = quote_plus("|".join(waypoints)) if waypoints else ""
        url = f"https://www.google.com/maps/dir/?api=1&travelmode={mode}&origin={origin}&destination={dest}"
        if wp:
            url += f"&waypoints={wp}"
        return url
    else:
        rpts = [f"{start_lat},{start_lon}"] + [f"{s['lat']},{s['lon']}" for s in stops]
        rtext = "~".join(rpts)
        ym_mode = mode
        return f"https://yandex.ru/maps/?rtext={quote_plus(rtext)}&rtt={ym_mode}"


# --- Доп. утилиты для оценки расстояний ---
def _haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    R = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, [a_lat, a_lon, b_lat, b_lon])
    dlat = la2 - la1
    dlon = lo2 - lo1
    h = math.sin(dlat / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


_SPEEDS_KMH = {
    "walk": 4.5,
    "bike": 15.0,
    "scooter": 15.0,
    "car": 30.0,
    "transit": 20.0,
}


def _ensure_stops_and_summary(route: Dict[str, Any]) -> Dict[str, Any]:
    """
    Нормализует структуру маршрута под стандартный формат.
    """
    if "stops" in route and "summary" in route:
        s = route["summary"]
        transport = s.get("transport", "walk")
        speed = _SPEEDS_KMH.get(transport, 4.5)
        stops = route["stops"]

        if stops:
            s.setdefault("start_lat", stops[0].get("lat"))
            s.setdefault("start_lon", stops[0].get("lon"))
            s.setdefault("start_label", s.get("start_label") or "Старт")

            total_km = 0.0
            prev = (s["start_lat"], s["start_lon"])
            for i, p in enumerate(stops):
                leg = p.get("leg_min")
                if leg in (None, 0):
                    dist = _haversine_km(prev[0], prev[1], p["lat"], p["lon"])
                    total_km += dist
                    p["leg_min"] = int(round(dist / speed * 60))
                else:
                    dist = _haversine_km(prev[0], prev[1], p["lat"], p["lon"])
                    total_km += dist
                if p.get("stay_min") is None:
                    p["stay_min"] = 10
                prev = (p["lat"], p["lon"])

            s["total_km"] = round(s.get("total_km") or total_km, 1)
            if not s.get("eta_min"):
                s["eta_min"] = int(sum(p["leg_min"] + p.get("stay_min", 0) for p in stops))
        return route

    # fallback-форма
    steps = route.get("steps") or []
    transport = route.get("transport", "walk")
    speed = _SPEEDS_KMH.get(transport, 4.5)

    if steps:
        start_lat = route.get("start_lat", steps[0]["lat"])
        start_lon = route.get("start_lon", steps[0]["lon"])
    else:
        start_lat = route.get("start_lat")
        start_lon = route.get("start_lon")

    stops: List[Dict[str, Any]] = []
    prev = (start_lat, start_lon) if start_lat is not None and start_lon is not None else None
    total_km = 0.0

    for i, p in enumerate(steps, 1):
        name = p.get("name") or p.get("title") or p.get("label") or f"Точка {i}"
        desc = p.get("description") or p.get("addr") or p.get("address") or ""
        lat, lon = p["lat"], p["lon"]

        if prev:
            dist = _haversine_km(prev[0], prev[1], lat, lon)
            leg_min = int(round(dist / speed * 60))
            total_km += dist
        else:
            dist = 0.0
            leg_min = 0

        stops.append({
            "name": name,
            "description": desc,
            "lat": lat,
            "lon": lon,
            "leg_min": leg_min,
            "stay_min": p.get("stay_min", 10),
        })
        prev = (lat, lon)

    eta_min = route.get("duration_min")
    if not eta_min:
        eta_min = int(sum(s["leg_min"] + s.get("stay_min", 0) for s in stops))

    return {
        "stops": stops,
        "summary": {
            "transport": transport,
            "start_lat": start_lat,
            "start_lon": start_lon,
            "start_label": route.get("start_label") or "Старт",
            "total_km": round(route.get("distance_km") or total_km, 1),
            "eta_min": max(1, int(eta_min)),
            "start_time": route.get("start_time"),
            "end_time": route.get("end_time"),
        },
    }


# --- Основной класс форматирования ---
class RouteFormatter:
    @staticmethod
    def format_route(route: Dict[str, Any], interests: str, time_hours: float) -> str:
        route = _ensure_stops_and_summary(route)
        stops = route.get("stops", [])
        s = route.get("summary", {})
        if not stops:
            return "⚠️ Не удалось собрать точки. Попробуйте уточнить интересы или поменять район."

        transport = s.get("transport", "walk")
        g_mode = _mode_to_gmaps(transport)
        y_mode = _mode_to_yamaps(transport)
        start_label = s.get("start_label") or "Старт"
        start_lat = s.get("start_lat", stops[0]["lat"])
        start_lon = s.get("start_lon", stops[0]["lon"])

        # форматирование времени маршрута
        start_time = _fmt_hhmm(s.get("start_time"))
        end_time = _fmt_hhmm(s.get("end_time"))
        eta_min = s.get("eta_min", int(time_hours * 60))

        time_text = f"🕒 Время: {start_time} — {end_time} ({_fmt_time_min(eta_min)})"

        title = (
            f"🎯 Персональный маршрут на {_fmt_time_min(int(time_hours * 60))}\n"
            f"Тема: {interests.strip()}\n\n"
            f"Старт: {start_label}\n"
            f"{time_text}\n\n"
            f"📍 Основные точки:\n"
        )

        lines = [title]
        for i, p in enumerate(stops, 1):
            name = p.get("name", f"Точка {i}")
            desc = p.get("description") or ""
            leg = f"⏱ ~{_fmt_time_min(p.get('leg_min', 0))} (+{_fmt_time_min(p.get('stay_min', 0))} на месте)"
            g = _map_link_point(p["lat"], p["lon"], "google")
            y = _map_link_point(p["lat"], p["lon"], "yandex")
            lines.append(
                f"{i}. {name}\n"
                f"   📖 {desc}\n"
                f"   🔗 [Google]({g}) · [Яндекс]({y})\n"
                f"   {leg}\n"
            )

        total_km = s.get("total_km", 0.0)
        lines.append(f"\n🧭 Длина ~ {total_km} км · Время ~ {_fmt_time_min(eta_min)}\n")

        g_route = _map_link_route(start_lat, start_lon, stops, provider="google", mode=g_mode)
        y_route = _map_link_route(start_lat, start_lon, stops, provider="yandex", mode=y_mode)
        lines.append(f"🗺️ Маршрут целиком: [Google]({g_route}) · [Яндекс]({y_route})")

        return "\n".join(lines)

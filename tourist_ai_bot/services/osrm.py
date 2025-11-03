import requests
from typing import List, Tuple, Optional

OSRM_TABLE = "https://router.project-osrm.org/table/v1/{profile}/{coords}"
OSRM_ROUTE = "https://router.project-osrm.org/route/v1/{profile}/{coords}?overview=false&steps=false"

def osrm_table(coords: List[Tuple[float, float]], profile: str = "foot") -> Optional[List[List[float]]]:
    """
    Возвращает матрицу durations (секунды) для списка координат.
    coords: [(lon,lat), ...]  — ВАЖНО: OSRM ждёт lon,lat
    """
    if len(coords) < 2:
        return [[0.0]]
    coord_str = ";".join(f"{x[0]},{x[1]}" for x in coords)
    url = OSRM_TABLE.format(profile=profile, coords=coord_str)
    r = requests.get(url, timeout=25)
    if r.status_code != 200:
        return None
    j = r.json()
    return j.get("durations")


def osrm_route_duration_order(order_coords: List[Tuple[float, float]], profile: str = "foot") -> Optional[float]:
    """Опционально: оценивает длительность уже упорядоченного маршрута (сек)."""
    if len(order_coords) < 2:
        return 0.0
    coord_str = ";".join(f"{x[0]},{x[1]}" for x in order_coords)
    url = OSRM_ROUTE.format(profile=profile, coords=coord_str)
    r = requests.get(url, timeout=25)
    if r.status_code != 200:
        return None
    j = r.json()
    routes = j.get("routes") or []
    if not routes:
        return None
    return routes[0].get("duration")


def nn_two_opt_with_matrix(durations: List[List[float]]) -> List[int]:
    """
    Находим порядок NN+2-opt по матрице длительностей (сек).
    Возвращает список индексов.
    """
    n = len(durations)
    if n <= 2:
        return list(range(n))

    # NN
    remaining = set(range(n))
    path = [0]
    remaining.remove(0)
    while remaining:
        last = path[-1]
        nxt = min(remaining, key=lambda j: durations[last][j] or 1e12)
        path.append(nxt)
        remaining.remove(nxt)

    # 2-opt
    def length(ordr):
        s = 0.0
        for i in range(len(ordr) - 1):
            dij = durations[ordr[i]][ordr[i + 1]] or 1e12
            s += dij
        return s

    best = path[:]
    best_len = length(best)
    improved = True
    while improved:
        improved = False
        for i in range(1, len(best) - 2):
            for k in range(i + 1, len(best) - 1):
                new = best[:i] + best[i:k + 1][::-1] + best[k + 1:]
                nl = length(new)
                if nl + 1e-9 < best_len:
                    best, best_len, improved = new, nl, True
                    break
            if improved:
                break
    return best

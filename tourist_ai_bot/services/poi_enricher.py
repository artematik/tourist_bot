import json
import logging
import re
import asyncio
import random
from typing import Any, Dict, List, Optional, Tuple

import httpx
from config import settings

logger = logging.getLogger(__name__)

# ---------------- Heuristics: address-like and generic names ----------------

_ADDR_WORDS_RU = [
    "ул.", "улица", "пр-т", "проспект", "пл.", "площадь", "пер.", "переулок",
    "ш.", "шоссе", "наб.", "набережная", "пр-д", "проезд", "кв.", "квартира",
    "дом", "д.", "стр.", "строение", "Россия", "Российская Федерация",
    "Нижний Новгород", "Нижегородская область", "область", "район"
]
_ADDR_WORDS_EN = [
    "st.", "st ", "street", "ave", "avenue", "blvd", "boulevard", "sq", "square",
    "road", "rd", "lane", "ln", "highway", "hwy", "embankment", "quay", "Russia",
    "Oblast", "District"
]
_ADDR_RE = re.compile(
    r"(\b\d{1,4}\b|"
    r"\b[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁа-яё\.-]+){0,3}\s+(?:ул\.|улица|пр-т|проспект|пл\.|площадь|пер\.|переулок|ш\.|шоссе|наб\.|набережная|пр-д|проезд)\b|"
    r"\b\w+\s+(street|st\.|avenue|ave|boulevard|blvd|road|rd|lane|ln|highway|hwy|embankment|quay)\b)",
    re.IGNORECASE
)

def _is_address_like(text: Optional[str]) -> bool:
    if not text:
        return True
    t = text.strip()
    if len(t) < 6:
        return True
    if _ADDR_RE.search(t):
        return True
    low = t.lower()
    for w in _ADDR_WORDS_RU:
        if w.lower() in low:
            return True
    for w in _ADDR_WORDS_EN:
        if w.lower() in low:
            return True
    if len(re.findall(r"\d", t)) >= 4:
        return True
    return False

def _looks_generic_name(name: Optional[str]) -> bool:
    n = (name or "").strip().lower()
    if not n or n in {"russia", "россия"}:
        return True
    if n.endswith(" russia") or n.endswith(" россия"):
        return True
    if n in {"nizhny novgorod", "нижний новгород"}:
        return True
    if ", russia" in n or "нижегородская область" in n:
        return True
    return False

def _needs_enrich(name: Optional[str], desc: Optional[str]) -> bool:
    if _looks_generic_name(name):
        return True
    if not desc:
        return True
    d = desc.strip()
    if len(d) < 20:
        return True
    if _is_address_like(d):
        return True
    return False

# ---------------- Local fallback templates (varied) ----------------

_FALLBACK_TEMPLATES = {
    "cafe": [
        "{name} — камерная кофейня с классикой (эспрессо, капучино) и выпечкой; уместная короткая остановка по пути.",
        "{name} — уютное место с базовыми кофейными напитками; хорошо зайти на 10–15 минут перед следующей точкой.",
        "{name} — небольшая точка с простым меню кофе и десертов; подойдёт для короткого перерыва.",
        "{name} — спокойная кофейня без претензий: берите напиток навынос и двигайтесь по маршруту.",
    ],
    "park": [
        "{name} — зелёная зона для неторопливой прогулки; несколько скамеек и тень для передышки.",
        "{name} — компактный сквер с аллеями; удобно сделать короткую остановку и свериться с маршрутом.",
        "{name} — тихий парк для небольшого круга и фото; подходящее место перед следующей точкой.",
        "{name} — открытое пространство для прогулки и короткого отдыха; можно задержаться на 10–15 минут.",
    ],
    "museum": [
        "{name} — небольшое музейное пространство; уместна короткая экспозиционная пауза без подробного осмотра.",
        "{name} — компактный музей; можно заглянуть на основную экспозицию и продолжить маршрут.",
        "{name} — локальная коллекция; оцените главное и двигайтесь дальше по плану.",
        "{name} — точка для краткого культурного акцента; не углубляясь, продолжайте прогулку.",
    ],
    "view": [
        "{name} — точка с обзорной перспективой; хорошо для быстрых фото и ориентира по маршруту.",
        "{name} — смотровая точка; задержитесь ненадолго ради вида и двигайтесь дальше.",
        "{name} — место с открытым видом; уместна короткая фотопауза.",
        "{name} — обзорная площадка; 5–10 минут будет достаточно.",
    ],
    "generic": [
        "{name} — интересная точка по теме маршрута; краткая остановка вписывается в тайминг.",
        "{name} — место по заявленной теме; удобная короткая пауза перед следующим пунктом.",
        "{name} — неброская, но уместная точка; оцените быстро и идите дальше.",
        "{name} — логичная остановка по пути; несколько минут — и к следующей локации.",
    ],
}

def _topic_key(interests: str, name: str) -> str:
    s = (interests or "").lower() + " " + (name or "").lower()
    if any(k in s for k in ["кафе", "coffee", "кофе", "cafe"]):
        return "cafe"
    if any(k in s for k in ["парк", "сквер", "park"]):
        return "park"
    if any(k in s for k in ["музей", "museum"]):
        return "museum"
    if any(k in s for k in ["вид", "панорама", "панорам", "viewpoint", "lookout", "обзор"]):
        return "view"
    return "generic"

def _fallback_description(name: str, interests: str) -> str:
    key = _topic_key(interests, name)
    templates = _FALLBACK_TEMPLATES[key]
    # детерминированная вариативность по имени
    idx = abs(hash(name)) % len(templates)
    return templates[idx].format(name=name or "Локация")

# ---------------- Ionet client + robust JSON extraction ----------------

class PoiEnricher:
    def __init__(self) -> None:
        self.api_key: str = settings.IONET_API_KEY
        self.base_url: str = "https://api.intelligence.io.solutions/api/v1"
        primary = getattr(settings, "POI_ENRICH_MODEL", None)
        # порядок: конфиг → 2 альтернативы
        self.model_candidates: List[str] = [m for m in [
            primary,
            "meta-llama/Llama-3.3-70B-Instruct",
            "mistralai/Mistral-Large-Instruct-2411",
            "mistralai/Mistral-Nemo-Instruct-2407",
        ] if m]

        # in-memory cache
        self._cache: Dict[Tuple[str, float, float, str, str], str] = {}

        # ограничим за вызов (меньше шанс словить 429)
        self.max_enrich_per_call: int = int(getattr(settings, "POI_ENRICH_MAX", 4))

    def _cache_key(self, name: str, lat: float, lon: float, locale: str, interests: str) -> Tuple[str, float, float, str, str]:
        return (name.strip(), round(float(lat), 6), round(float(lon), 6), locale, (interests or "").strip().lower())

    @staticmethod
    def _extract_json(content: Any) -> Optional[Dict[str, Any]]:
        if isinstance(content, dict):
            return content
        if not isinstance(content, str):
            return None
        txt = content.strip()
        try:
            return json.loads(txt)
        except Exception:
            pass
        m = re.search(r"\{[\s\S]*\}", txt)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        m2 = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt, re.IGNORECASE)
        if m2:
            try:
                return json.loads(m2.group(1))
            except Exception:
                pass
        return None

    async def _try_call_once(self, model: str, payload: Dict[str, Any], headers: Dict[str, str]) -> Tuple[Optional[Dict[str, Any]], bool]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            if resp.status_code == 429:
                logger.warning("POI Enricher HTTP 429. Body: %s", resp.text)
                return None, True  # (no data, retryable)
            if resp.is_error:
                logger.warning("POI Enricher HTTP %s. Body: %s", resp.status_code, resp.text)
                return None, False
            data = resp.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            return self._extract_json(content), False

    async def _call_llm_with_backoff(self, system_prompt: str, user_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        retry_delay = 0.6
        for turn in range(2):  # два круга по пулу моделей
            for model in self.model_candidates:
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                    ],
                    "temperature": 0.5,
                }
                parsed, retryable = await self._try_call_once(model, payload, headers)
                if parsed:
                    return parsed
                if retryable:
                    # бэкофф с джиттером
                    await asyncio.sleep(retry_delay + random.random() * 0.4)
            retry_delay *= 1.7
        return None

    async def enrich_stops(self, stops: List[Dict[str, Any]], *, interests: str, locale: str = "ru") -> List[Dict[str, Any]]:
        if not stops:
            return stops

        # приоритезируем самые пустые
        to_enrich_idx: List[int] = []
        for i, s in enumerate(stops):
            if _needs_enrich(s.get("name"), s.get("description")):
                to_enrich_idx.append(i)

        if not to_enrich_idx:
            return stops

        to_enrich_idx = to_enrich_idx[: self.max_enrich_per_call]

        # применим кэш
        batch: List[Tuple[int, Dict[str, Any]]] = []
        for i in to_enrich_idx:
            s = stops[i]
            key = self._cache_key(s.get("name") or "", float(s.get("lat")), float(s.get("lon")), locale, interests)
            cached = self._cache.get(key)
            if cached:
                stops[i] = {**s, "description": cached}
            else:
                batch.append((i, s))

        if not batch:
            return stops

        items = []
        for i, s in batch:
            items.append({
                "idx": i,
                "name": s.get("name") or "",
                "lat": float(s.get("lat")),
                "lon": float(s.get("lon")),
            })

        system_prompt = (
            "You are a concise travel guide. "
            "For each place, write 1–2 sentences in the requested language with concrete, non-generic facts "
            "about THIS exact place at the given coordinates. "
            "Avoid city/district background unless it's part of the official name. "
            "No prices/hours, no links, no addresses."
        )
        user_payload = {
            "locale": locale,
            "topic_hint": interests,
            "places": items,
            "output_schema": {
                "type": "object",
                "properties": {
                    "descriptions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "idx": {"type": "number"},
                                "description": {"type": "string"}
                            },
                            "required": ["idx", "description"]
                        }
                    }
                },
                "required": ["descriptions"]
            },
            "instruction": (
                "Return ONLY valid JSON matching `output_schema`. "
                "Language: '{locale}'. Tone: precise and varied (avoid repeating the same phrasing). "
                "Ground strictly on the place and coordinates."
            ).format(locale=locale)
        }

        parsed = await self._call_llm_with_backoff(system_prompt, user_payload)

        # если не получилось (квота/ошибка) — разнообразный локальный фолбэк
        if not parsed or not isinstance(parsed, dict) or not isinstance(parsed.get("descriptions"), list):
            for i, s in batch:
                desc = _fallback_description(s.get("name") or "Локация", interests)
                stops[i] = {**s, "description": desc}
                key = self._cache_key(s.get("name") or "", float(s.get("lat")), float(s.get("lon")), locale, interests)
                self._cache[key] = desc
            return stops

        # применяем ответы и кладём в кэш
        for obj in parsed["descriptions"]:
            if not isinstance(obj, dict):
                continue
            idx = obj.get("idx")
            desc = obj.get("description")
            if isinstance(idx, (int, float)) and isinstance(desc, str) and len(desc.strip()) >= 8:
                i = int(idx)
                if 0 <= i < len(stops):
                    s = stops[i]
                    new_desc = desc.strip()
                    stops[i] = {**s, "description": new_desc}
                    key = self._cache_key(s.get("name") or "", float(s.get("lat")), float(s.get("lon")), locale, interests)
                    self._cache[key] = new_desc

        return stops

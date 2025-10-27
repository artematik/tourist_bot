import logging
import random
from typing import Dict, Any
from datetime import datetime, timedelta
import json
import re
import requests
from config import settings


class AIService:
    def __init__(self):
        """Инициализация клиента IO.net"""
        self.api_key = settings.IONET_API_KEY
        self.base_url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

        if not self.api_key:
            raise ValueError("❌ Не найден IONET_API_KEY в .env")

    def clean_json(self, text: str) -> str:
        """Удаляет Markdown-обёртку и извлекает чистый JSON"""
        # Убираем блоки ```json ... ```
        text = re.sub(r"^```(json)?", "", text.strip())
        text = re.sub(r"```$", "", text.strip())
        # Убираем всё до первой и после последней фигурной скобки
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return match.group(0) if match else text

    def generate_route(self, interests, time_hours, location, lat=None, lon=None):
        """
        Создаёт туристический маршрут с помощью IO.net API
        """
        prompt = (
            "Ты — профессиональный гид по Нижнему Новгороду. "
            "Создай оптимальный туристический маршрут в формате JSON.\n"
            "Формат ответа:\n"
            "{"
            " 'route_summary': str,"
            " 'points': ["
            "   { 'name': str, 'description': str, 'reason': str, 'lat': float, 'lon': float }"
            " ],"
            " 'path_description': str,"
            " 'timeline': [str]"
            "}\n\n"
            f"Интересы: {interests}\n"
            f"Время прогулки: {time_hours} часов\n"
            f"Город: {location}\n"
            f"Координаты старта: {lat}, {lon}\n"
            "Ответ строго в виде JSON без пояснений и текста вокруг."
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        body = {
            "model": "meta-llama/Llama-3.3-70B-Instruct",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
            "max_tokens": 800,
        }

        response = requests.post(self.base_url, headers=headers, json=body)

        if response.status_code != 200:
            raise Exception(
                f"❌ Ошибка IO.net API ({response.status_code}): {response.text}"
            )

        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        if not content:
            raise ValueError("⚠️ Пустой ответ от модели.")

        # 🧹 Очищаем markdown и пробуем парсить JSON
        cleaned = self.clean_json(content)

        try:
            parsed = json.loads(cleaned)
            return parsed
        except json.JSONDecodeError as e:
            # Если всё ещё невалидный JSON — возвращаем текст и ошибку
            return {"raw_text": cleaned, "error": f"❌ Ошибка JSON: {e}"}

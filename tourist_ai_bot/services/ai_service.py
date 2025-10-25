import logging
import random
from typing import Dict, Any
from datetime import datetime, timedelta

class AIService:
    """Умный сервис генерации маршрутов БЕЗ реального AI"""
    
    async def generate_route(self, interests: str, time_hours: float, location: str, lat: float = None, lon: float = None) -> Dict[str, Any]:
        """
        Генерирует персонализированный маршрут на основе интересов
        """
        logging.info(f"🎯 Генерируем умный маршрут для: {interests}")
        return self._get_smart_fallback_route(interests, time_hours, location)
    
    def _get_smart_fallback_route(self, interests: str, time_hours: float, location: str) -> Dict[str, Any]:
        """Умный fallback на основе интересов пользователя"""
        
        interests_lower = interests.lower()
        
        # Базовые точки для всех маршрутов
        base_points = [
            {
                "name": "Нижегородский кремль",
                "description": "Исторический центр города с прекрасным видом на Волгу",
                "reason": "Сердце Нижнего Новгорода с богатой историей",
                "estimated_time_min": 60
            },
            {
                "name": "Большая Покровская улица",
                "description": "Главная пешеходная улица с историческими зданиями",
                "reason": "Идеальное место для прогулок и знакомства с городской атмосферой",
                "estimated_time_min": 45
            }
        ]
        
        # Точки по категориям интересов
        interest_points = []
        
        # Кофейни и еда
        if any(word in interests_lower for word in ['кофе', 'кафе', 'еда', 'ресторан', 'кухн', 'завтрак', 'обед', 'ужин']):
            interest_points.extend([
                {
                    "name": "Кафе «Холст»",
                    "description": "Уютное кафе с местной кухней и авторским кофе",
                    "reason": "Отличное место чтобы попробовать местную кухню и выпить кофе",
                    "estimated_time_min": 45
                }
            ])
        
        # Искусство и культура
        if any(word in interests_lower for word in ['искусство', 'арт', 'стрит-арт', 'граффити', 'культур', 'творчество']):
            interest_points.extend([
                {
                    "name": "Арт-галерея «Рекорд»",
                    "description": "Центр современного искусства и стрит-арта",
                    "reason": "Лучшее место для любителей современного искусства",
                    "estimated_time_min": 50
                }
            ])
        
        # Виды и панорамы
        if any(word in interests_lower for word in ['вид', 'панорам', 'волг', 'река', 'фото', 'съемк', 'пейзаж']):
            interest_points.extend([
                {
                    "name": "Чкаловская лестница",
                    "description": "Знаменитая лестница с панорамным видом на Волгу",
                    "reason": "Лучшая панорама города и реки для фотографий",
                    "estimated_time_min": 35
                }
            ])
        
        # История и архитектура
        if any(word in interests_lower for word in ['история', 'музей', 'архитектур', 'старин', 'историческ']):
            interest_points.extend([
                {
                    "name": "Усадьба Рукавишниковых",
                    "description": "Роскошный исторический особняк XIX века",
                    "reason": "Интересный образец старинной архитектуры и истории",
                    "estimated_time_min": 55
                }
            ])
        
        # Если интересы не распознаны, добавляем популярные места
        if not interest_points:
            interest_points = [
                {
                    "name": "Чкаловская лестница",
                    "description": "Знаменитая лестница с видом на Волгу",
                    "reason": "Одна из главных достопримечательностей города",
                    "estimated_time_min": 35
                }
            ]
        
        # Выбираем 1-2 дополнительные точки
        random.shuffle(interest_points)
        additional_points = interest_points[:2]
        
        # Комбинируем все точки
        all_points = base_points + additional_points
        
        # Ограничиваем общее время
        final_points = self._adjust_for_time(all_points, time_hours)
        
        return {
            "route_summary": f"Маршрут по Нижнему Новгороду с учетом ваших интересов: {interests}",
            "points": final_points,
            "path_description": self._generate_path_description(final_points, location),
            "timeline": self._generate_timeline(final_points, time_hours)
        }
    
    def _adjust_for_time(self, points: list, total_hours: float) -> list:
        """Подбирает точки чтобы уложиться во время"""
        total_minutes = total_hours * 60
        transition_time = (len(points) - 1) * 15
        
        available_time = total_minutes - transition_time
        
        selected_points = [points[0], points[1]]
        available_time -= (points[0]['estimated_time_min'] + points[1]['estimated_time_min'])
        
        for point in points[2:]:
            if available_time >= point['estimated_time_min']:
                selected_points.append(point)
                available_time -= point['estimated_time_min']
        
        return selected_points
    
    def _generate_path_description(self, points: list, start_location: str) -> str:
        """Генерирует описание маршрута"""
        point_names = [point['name'] for point in points]
        
        if len(points) >= 3:
            return f"Маршрут начинается от {start_location}, проходит через {point_names[0]}, затем к {point_names[1]} и завершается у {point_names[2]}"
        else:
            return f"Маршрут начинается от {start_location} и проходит через {' и '.join(point_names)}"
    
    def _generate_timeline(self, points: list, total_hours: float) -> list:
        """Генерирует таймлайн"""
        timeline = []
        current_time = "14:00"
        
        for i, point in enumerate(points):
            end_time = self._add_minutes(current_time, point['estimated_time_min'])
            timeline.append(f"{current_time} - {end_time}: Осмотр {point['name']}")
            current_time = end_time
            
            if i < len(points) - 1:
                transition_time = 15
                end_transition = self._add_minutes(current_time, transition_time)
                timeline.append(f"{current_time} - {end_transition}: Переход к {points[i+1]['name']}")
                current_time = end_transition
        
        return timeline
    
    def _add_minutes(self, time_str: str, minutes: int) -> str:
        """Добавляет минуты к времени"""
        time_obj = datetime.strptime(time_str, "%H:%M")
        new_time = time_obj + timedelta(minutes=minutes)
        return new_time.strftime("%H:%M")
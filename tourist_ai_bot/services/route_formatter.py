from typing import Dict, Any

class RouteFormatter:
    """Класс для форматирования маршрута в красивое сообщение"""
    
    @staticmethod
    def format_route(route_data: Dict[str, Any], interests: str, time_hours: float) -> str:
        """Форматирует данные маршрута в читаемое сообщение"""
        
        message = f"🎯 **Вот ваш персонализированный маршрут на {time_hours} часа!**\n\n"
        message += f"*Тема:* {route_data['route_summary']}\n\n"
        
        message += "📍 **Основные точки:**\n"
        for i, point in enumerate(route_data['points'], 1):
            message += f"\n{i}. *{point['name']}*\n"
            message += f"   📖 {point['description']}\n"
            message += f"   💡 {point['reason']}\n"
            est_time = point.get('estimated_time_min', 30)  # 👈 безопасный доступ
            message += f"   ⏱ ~{est_time} мин\n"

        
        message += f"\n🗺️ **Ваш маршрут:**\n{route_data['path_description']}\n"
        
        message += f"\n⏱️ **План прогулки:**\n"
        for timeline_item in route_data['timeline']:
            message += f"• {timeline_item}\n"
        
        message += "\nПриятной прогулки по Нижнему Новгороду! ❤️"
        
        return message
    
    @staticmethod
    def format_error_message() -> str:
        """Сообщение об ошибке"""
        return (
            "😔 К сожалению, не удалось сгенерировать маршрут.\n\n"
            "Попробуйте начать заново командой /start"
        )

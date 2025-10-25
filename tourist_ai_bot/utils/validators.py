from config import settings

def validate_interests(interests: str) -> bool:
    """Валидация введенных интересов"""
    return (len(interests) >= settings.MIN_INTERESTS_LENGTH and 
            len(interests) <= settings.MAX_INTERESTS_LENGTH)

def validate_time(time_text: str) -> float:
    """Валидация и преобразование времени"""
    if time_text.endswith('+'):
        time_text = time_text[:-1]
    
    try:
        time_hours = float(time_text)
    except ValueError:
        raise ValueError("Пожалуйста, введите число (например: 1, 2, 3.5)")
    
    if time_hours < settings.MIN_TIME_HOURS:
        raise ValueError(f"Минимальное время для прогулки - {settings.MIN_TIME_HOURS} часа")
    
    if time_hours > settings.MAX_TIME_HOURS:
        raise ValueError(f"Максимальное время для прогулки - {settings.MAX_TIME_HOURS} часов")
    
    return time_hours
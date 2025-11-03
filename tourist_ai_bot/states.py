from aiogram.fsm.state import State, StatesGroup

class UserState(StatesGroup):
    interest = State()
    time = State()
    transport = State()
    location = State()
    awaiting_address_text = State()
    start_time = State()

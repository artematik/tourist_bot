from aiogram.fsm.state import State, StatesGroup

class UserState(StatesGroup):
    interest = State()
    time = State()
    location = State()
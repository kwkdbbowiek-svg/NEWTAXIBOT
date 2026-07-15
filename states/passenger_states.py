from aiogram.fsm.state import State, StatesGroup


class OrderCreation(StatesGroup):
    from_location = State()
    to_location = State()
    phone = State()
    passenger_count = State()

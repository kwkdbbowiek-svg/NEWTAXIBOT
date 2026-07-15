from aiogram.fsm.state import State, StatesGroup


class DriverRegistration(StatesGroup):
    full_name = State()
    phone = State()
    car_model = State()
    car_number = State()
    confirm = State()

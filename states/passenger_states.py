from aiogram.fsm.state import State, StatesGroup


class OrderCreation(StatesGroup):
    route = State()            # yo'nalish tanlash (Toshkent→Bekobod yoki aksi)
    phone = State()            # telefon raqam
    passenger_count = State()  # necha kishi yoki pochta
    cargo_description = State() # pochta tavsifi

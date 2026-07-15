from aiogram.fsm.state import State, StatesGroup


class AdminTopUp(StatesGroup):
    user_id = State()
    amount = State()


class AdminDeduct(StatesGroup):
    user_id = State()
    amount = State()


class AdminCommission(StatesGroup):
    new_value = State()


class AdminBroadcast(StatesGroup):
    message = State()


class AdminPrice(StatesGroup):
    route = State()    # qaysi yo'nalish narxi o'zgartiriladi
    price = State()    # yangi narx

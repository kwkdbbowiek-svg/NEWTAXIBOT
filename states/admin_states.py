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

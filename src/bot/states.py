from aiogram.fsm.state import State, StatesGroup


class BuyStates(StatesGroup):
    choosing_size = State()
    choosing_quantity = State()
    confirming = State()
    choosing_payment = State()


class TopUpStates(StatesGroup):
    entering_amount = State()
    waiting_for_payment = State()


class PromoStates(StatesGroup):
    entering_code = State()


class AdminStates(StatesGroup):
    waiting_for_excel = State()
    waiting_for_user_id = State()
    waiting_for_balance_amount = State()
    waiting_for_ban_user_id = State()
    creating_promo_type = State()
    creating_promo_value = State()
    creating_promo_uses = State()
    waiting_for_welcome_photo = State()


class BroadcastStates(StatesGroup):
    entering_text = State()
    confirming = State()

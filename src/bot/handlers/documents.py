import os

from aiogram import F, Router, types

from src.bot.keyboards.inline import user_main_kb

router = Router()

DOCUMENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "documents")

DOCUMENTS = {
    "doc:privacy": {
        "file": "privacy_policy.html",
        "title": "📄 Политика конфиденциальности",
        "caption": "📄 <b>Политика конфиденциальности</b>\n\nДокумент в формате HTML. Откроется в браузере.",
    },
    "doc:agreement": {
        "file": "user_agreement.html",
        "title": "📄 Пользовательское соглашение",
        "caption": "📄 <b>Пользовательское соглашение</b>\n\nДокумент в формате HTML. Откроется в браузере.",
    },
}


@router.callback_query(F.data.in_(DOCUMENTS))
async def send_document(callback: types.CallbackQuery):
    doc = DOCUMENTS[callback.data]
    file_path = os.path.join(DOCUMENTS_DIR, doc["file"])

    if not os.path.exists(file_path):
        await callback.message.answer("❌ Документ временно недоступен.")
        await callback.answer()
        return

    await callback.message.answer_document(
        types.input_file.FSInputFile(file_path, filename=doc["file"]),
        caption=doc["caption"],
        reply_markup=user_main_kb(),
    )
    await callback.answer()

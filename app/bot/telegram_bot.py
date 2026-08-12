from __future__ import annotations

import traceback

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from urllib.parse import urlencode

from app.config import settings
from app.database.session import SessionLocal, init_db
from app.logging import get_logger
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.services.admin_alert_service import ADMIN_ERROR_PREFIX, send_admin_alert
from app.services.admin_report_service import build_admin_report_message, get_admin_report_stats
from app.services.product_service import ProductService

logger = get_logger("app.bot.telegram_bot")


def is_admin_user(update: Update) -> bool:
    admin_id = (settings.ADMIN_TELEGRAM_ID or "").strip()
    if not admin_id or update.effective_user is None:
        return False

    return str(update.effective_user.id) == admin_id


def build_help_message(is_admin: bool = False) -> str:
    message = (
        "Olá! Eu monitoro preços de livros na Amazon e te aviso quando eles baixarem! 📚\n\n"
        "Comandos disponíveis:\n"
        "• /livro — adiciona um livro na lista de monitoramento através de um link da Amazon\n"
        "• /lista — vê os livros que você está monitorando (máx. 5)\n"
        "• /remover — remove um livro da sua lista\n"
        "• /status — mostra o preço atual de um livro selecionado\n"
        "• /ajuda — mostra esta mensagem novamente"
    )

    if is_admin:
        message += "\n• /relatorio — mostra métricas gerais do sistema (admin)"

    return message


def build_removal_keyboard(products: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"❌ {product.title or product.asin}", callback_data=f"remove:{product.id}")]
        for product in products
    ]
    return InlineKeyboardMarkup(buttons)


def build_status_keyboard(products: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(product.title or product.asin, callback_data=f"status:{product.id}")]
        for product in products
    ]
    return InlineKeyboardMarkup(buttons)


def build_product_affiliate_link(product: Product) -> str | None:
    if product.affiliate_link:
        return product.affiliate_link

    if not settings.AMAZON_PARTNER_TAG:
        return None

    base_url = f"https://www.amazon.com.br/dp/{product.asin}"
    params = {"tag": settings.AMAZON_PARTNER_TAG}
    return f"{base_url}?{urlencode(params)}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = SessionLocal()
    try:
        service = ProductService(db)
        user = update.effective_user
        service.get_or_create_user(
            str(user.id),
            username=user.username,
            first_name=user.first_name,
        )
        await update.message.reply_text(build_help_message(is_admin=is_admin_user(update)))
    finally:
        db.close()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(build_help_message(is_admin=is_admin_user(update)))


async def relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin_user(update):
        await update.message.reply_text("⛔ Comando disponível apenas para o administrador.")
        return

    db = SessionLocal()
    try:
        stats = get_admin_report_stats(db)
        await update.message.reply_text(build_admin_report_message(stats))
    finally:
        db.close()


async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = SessionLocal()
    try:
        service = ProductService(db)
        products = service.list_products(str(update.effective_user.id))
        if not products:
            await update.message.reply_text("Você ainda não está monitorando nenhum livro.")
            return

        lines = [f"{index}. {product.title or product.asin}" for index, product in enumerate(products, start=1)]
        await update.message.reply_text("📚 Livros monitorados:\n" + "\n".join(lines))
    finally:
        db.close()


async def livro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📲 Envie o link da Amazon do livro que deseja monitorar.")


async def remover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = SessionLocal()
    try:
        service = ProductService(db)
        products = service.list_products(str(update.effective_user.id))
        if not products:
            await update.message.reply_text("Você ainda não está monitorando nenhum livro! Use o comando /livro para adicionar um.")
            return

        await update.message.reply_text(
            "Qual desses livros você quer remover? 🗑️",
            reply_markup=build_removal_keyboard(products),
        )
    finally:
        db.close()


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = SessionLocal()
    try:
        service = ProductService(db)
        products = service.list_products(str(update.effective_user.id))
        if not products:
            await update.message.reply_text("Você ainda não está monitorando nenhum livro! Use o comando /livro para adicionar um.")
            return

        await update.message.reply_text(
            "💡Escolha o livro para ver o status atual",
            reply_markup=build_status_keyboard(products),
        )
    finally:
        db.close()


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query:
        return

    await update.callback_query.answer()
    callback_data = update.callback_query.data or ""

    if callback_data.startswith("remove:"):
        product_id = callback_data.split(":", 1)[1]
        db = SessionLocal()
        try:
            service = ProductService(db)
            removed, message = service.remove_product(str(update.effective_user.id), product_id)
            await update.callback_query.edit_message_text(message)
        finally:
            db.close()
        return

    if callback_data.startswith("status:"):
        product_id = callback_data.split(":", 1)[1]
        db = SessionLocal()
        try:
            product = db.query(Product).filter(Product.id == int(product_id)).first()
            if not product:
                await update.callback_query.edit_message_text("Livro não encontrado.")
                return

            latest_price = (
                db.query(PriceHistory)
                .filter(PriceHistory.product_id == product.id)
                .order_by(PriceHistory.checked_at.desc())
                .first()
            )

            if latest_price and latest_price.price is not None:
                message = (
                    f"Status:\n📖 {product.title or product.asin}\n"
                    f"💵 Preço atual: R$ {latest_price.price:.2f}"
                )
            else:
                message = f"Status de {product.title or product.asin}\nAinda não há preço registrado para esse produto."

            affiliate_link = build_product_affiliate_link(product)
            keyboard_buttons = []
            if affiliate_link:
                keyboard_buttons.append([InlineKeyboardButton("🛒 Ver na Amazon", url=affiliate_link)])

            if keyboard_buttons:
                await update.callback_query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard_buttons))
            else:
                await update.callback_query.edit_message_text(message)
        finally:
            db.close()
        return


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    message_text = update.message.text.strip()
    if not message_text.startswith("http"):
        await update.message.reply_text(build_help_message(is_admin=is_admin_user(update)))
        return

    db = SessionLocal()
    try:
        service = ProductService(db)
        user_id = str(update.effective_user.id)
        service.get_or_create_user(
            user_id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )
        product, message = service.register_product(user_id, message_text)
        if product is None:
            await update.message.reply_text(message)
            return

        await update.message.reply_text(
            f"Livro cadastrado com sucesso: {product.title or product.asin}"
        )
    except Exception as exc:
        logger.exception("Erro ao processar mensagem do bot")
        send_admin_alert(
            f"{ADMIN_ERROR_PREFIX}\n\n"
            "Erro ao processar mensagem do usuário\n\n"
            f"Usuário: {getattr(update.effective_user, 'id', 'desconhecido')}\n"
            f"Erro: {str(exc)[:500]}"
        )
        await update.message.reply_text(f"Não foi possível processar seu pedido: {exc}")
    finally:
        db.close()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    logger.exception("Erro não tratado no Telegram bot", exc_info=error)

    try:
        error_text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        send_admin_alert(
            f"{ADMIN_ERROR_PREFIX}\n\n"
            f"{error_text[:3000]}"
        )
    except Exception:
        # Evita quebrar o fluxo de polling caso o alerta ao admin falhe.
        pass


def build_application() -> Application:
    init_db()
    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN or "").build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("livro", livro))
    application.add_handler(CommandHandler("ajuda", help_command))
    application.add_handler(CommandHandler("lista", lista))
    application.add_handler(CommandHandler("remover", remover))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("relatorio", relatorio))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_error_handler(error_handler)
    return application


def run_bot() -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN não configurado. O bot não será iniciado.")
        return

    application = build_application()
    logger.info("Iniciando bot do Telegram")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

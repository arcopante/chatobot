#!/usr/bin/env python3
"""
Bot MINIMALISTA para probar recepción de fotos
"""

import os
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = "token_telegram_del_bot_aqui"  # Reemplaza con tu token real
AUTHORIZED_USER_ID = user_id_telegram_para_md  # Reemplaza con tu ID de usuario real (numérico)

async def handle_ANY(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler que captura TODO"""
    print("\n" + "="*80)
    print("🔔 MENSAJE RECIBIDO!")
    print("="*80)
    
    if update.message:
        print(f"Chat type: {update.effective_chat.type}")
        print(f"User ID: {update.effective_user.id}")
        print(f"Has text: {bool(update.message.text)}")
        print(f"Has photo: {bool(update.message.photo)}")
        print(f"Has caption: {bool(update.message.caption)}")
        
        if update.message.text:
            print(f"Text: '{update.message.text}'")
            await update.message.reply_text(f"✅ Recibí TEXTO: {update.message.text}")
        
        if update.message.photo:
            print(f"Photo count: {len(update.message.photo)}")
            caption = update.message.caption or "(sin caption)"
            print(f"Caption: '{caption}'")
            await update.message.reply_text(f"✅ Recibí FOTO con caption: {caption}")
        
        if not update.message.text and not update.message.photo:
            print("⚠️  Mensaje sin texto ni foto")
            await update.message.reply_text("✅ Recibí algo (no texto ni foto)")
    
    print("="*80 + "\n")

async def main():
    print("\n🧪 BOT MINIMALISTA - PRUEBA DE RECEPCIÓN")
    print("="*80)
    print(f"Token: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-10:]}")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # UN SOLO HANDLER que captura TODO
    print("Registrando handler UNIVERSAL (filters.ALL)...")
    application.add_handler(MessageHandler(filters.ALL, handle_ANY))
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    print("✅ Bot iniciado")
    print("📱 Envía CUALQUIER COSA al bot y mira la consola")
    print("💡 Presiona Ctrl+C para detener\n")
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\n👋 Deteniendo...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    asyncio.run(main())

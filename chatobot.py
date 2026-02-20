#!/usr/bin/env python3
"""
Bot de Telegram conectado a LM Studio local con soporte para visión
Ejecutar en Mac Silicon o Linux con Python 3.10+ y LM Studio instalado localmente
Características:
- Responde a mensajes de texto e imágenes (compatible con modelos de visión como Qwen3-VL)
- Historial de conversación persistente usando SQLite
- Comandos para gestionar el historial, cargar modelos y ver estadísticas
- Sistema de mensajes aleatorios con preguntas generadas dinámicamente por el LLM
- Solo responde a un usuario autorizado (uso privado)
- Manejo avanzado de errores con mensajes claros para el usuario
- Logging optimizado para reducir ruido y enfocarse en errores críticos
Instrucciones:
1. Instalar dependencias: `pip install python-telegram-bot aiohttp`
2. Configurar variables de entorno:
   - TELEGRAM_TOKEN: Token de tu bot de Telegram
   - ALLOWED_USER_ID: ID de Telegram del usuario autorizado
   - SYSTEM_PROMPT: Prompt de sistema para definir el comportamiento del LLM
3. Ejecutar el bot: `python chatobot.py`
Nota: Asegúrate de que LM Studio esté ejecutándose localmente y que el modelo de visión (como Qwen3-VL) esté cargado para probar la funcionalidad de análisis de imágenes. Usa el comando /stats para verificar el estado del modelo activo.
"""

import os
import sys
import asyncio
import random
import base64
import sqlite3
import json
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import aiohttp

# Configurar logging para reducir ruido de la librería de Telegram
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING  # Solo mostrar warnings y errores críticos
)
# Silenciar específicamente los warnings de httpx y telegram
logging.getLogger('httpx').setLevel(logging.ERROR)
logging.getLogger('telegram').setLevel(logging.ERROR)
logging.getLogger('telegram.ext').setLevel(logging.ERROR)

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

# Token de tu bot de Telegram
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]

# ID de Telegram del usuario autorizado (reemplaza con tu ID)
# Para obtener tu ID, puedes usar @userinfobot en Telegram
AUTHORIZED_USER_ID = int(os.environ["ALLOWED_USER_ID"])

# URL de LM Studio (por defecto usa el puerto 1234)
LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"

# Tiempo mínimo y máximo entre mensajes aleatorios (en segundos)
# Para pruebas rápidas, usa valores pequeños como 60 y 180 (1-3 minutos)
MIN_RANDOM_MESSAGE_INTERVAL = 3600  # 1 hora (3600 para producción, 60 para pruebas)
MAX_RANDOM_MESSAGE_INTERVAL = 7200  # 2 horas (7200 para producción, 180 para pruebas)

# Probabilidad de enviar mensaje aleatorio (0.0 a 1.0)
# 0.3 = 30% de probabilidad, 1.0 = 100% siempre envía
RANDOM_MESSAGE_PROBABILITY = 0.5

# Prompt de sistema para definir el comportamiento del LLM
SYSTEM_PROMPT = os.environ["SYSTEM_PROMPT"]

# Nombre del archivo de base de datos
DB_FILE = "chatobot.db"

# ============================================================================
# VARIABLES GLOBALES
# ============================================================================

# Historial de conversación por usuario
conversation_history = {}

# Estadísticas
stats = {
    "messages_sent": 0,
    "messages_received": 0,
    "images_received": 0,
    "random_messages_sent": 0,
    "random_messages_skipped": 0,
    "start_time": datetime.now(),
    "llm_calls": 0,
    "errors": 0
}

# ============================================================================
# FUNCIONES DE BASE DE DATOS
# ============================================================================

def init_database():
    """
    Inicializa la base de datos SQLite y crea las tablas necesarias
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Tabla para almacenar mensajes del historial
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            has_image BOOLEAN DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Índice para búsquedas rápidas por usuario
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_user_id 
        ON conversation_history(user_id)
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Base de datos inicializada")


def load_conversation_history(user_id: int) -> list:
    """
    Carga el historial de conversación de un usuario desde la base de datos
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Cargar los últimos 20 mensajes del usuario
    cursor.execute('''
        SELECT role, content, has_image 
        FROM conversation_history 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT 20
    ''', (user_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    # Invertir para que estén en orden cronológico
    rows.reverse()
    
    # Convertir a formato de mensajes
    messages = []
    for role, content, has_image in rows:
        if has_image:
            # Si tenía imagen, intentar deserializar el JSON
            try:
                message = json.loads(content)
                messages.append(message)
            except:
                # Si falla, crear mensaje de texto simple
                messages.append({"role": role, "content": content})
        else:
            messages.append({"role": role, "content": content})
    
    if messages:
        print(f"📚 Cargados {len(messages)} mensajes del historial para usuario {user_id}")
    
    return messages


def save_message_to_db(user_id: int, role: str, message: dict):
    """
    Guarda un mensaje en la base de datos
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Determinar si el mensaje tiene imagen
    has_image = isinstance(message.get("content"), list)
    
    # Si tiene imagen, serializar como JSON
    if has_image:
        content = json.dumps(message)
    else:
        content = message.get("content", "")
    
    cursor.execute('''
        INSERT INTO conversation_history (user_id, role, content, has_image)
        VALUES (?, ?, ?, ?)
    ''', (user_id, role, content, has_image))
    
    conn.commit()
    conn.close()


def clear_conversation_history_db(user_id: int):
    """
    Elimina todo el historial de conversación de un usuario de la base de datos
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM conversation_history 
        WHERE user_id = ?
    ''', (user_id,))
    
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"🗑️  Eliminados {deleted} mensajes de la BD para usuario {user_id}")
    return deleted

# ============================================================================
# FUNCIONES DE AUTORIZACIÓN
# ============================================================================

def is_authorized(user_id: int) -> bool:
    """
    Verifica si el usuario está autorizado para usar el bot
    """
    return user_id == AUTHORIZED_USER_ID


async def check_authorization(update: Update) -> bool:
    """
    Verifica autorización y responde si el usuario no está autorizado
    También verifica que sea un chat privado (MD)
    """
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    
    # Verificar que sea un chat privado (MD)
    if chat_type != "private":
        print(f"⚠️  Mensaje ignorado de chat tipo '{chat_type}' (solo funciona en MD)")
        return False
    
    # Verificar autorización del usuario
    if not is_authorized(user_id):
        username = update.effective_user.username or "Usuario"
        print(f"⚠️  Intento de acceso no autorizado: {username} (ID: {user_id})")
        await update.message.reply_text(
            "❌ Lo siento, no estás autorizado para usar este bot.\n"
            "Este bot es de uso privado."
        )
        return False
    
    return True


# ============================================================================
# FUNCIONES DE LLM
# ============================================================================

async def call_lm_studio(messages, max_tokens=500):
    """
    Llama a LM Studio local y obtiene una respuesta
    Soporta mensajes multimodales (texto + imágenes)
    Adapta parámetros según el modelo cargado
    """
    try:
        # Verificar qué modelo está cargado
        is_online, model_info = await check_lm_studio_status()
        model_id = ""
        if is_online and model_info and "data" in model_info and len(model_info["data"]) > 0:
            model_id = model_info["data"][0].get("id", "").lower()
        
        # Preparar los mensajes con el system prompt al inicio
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
        
        # Configurar parámetros base
        payload = {
            "messages": full_messages,
            "temperature": 0.7,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        # Añadir parámetros anti-repetición solo para modelos compatibles
        # Gemma-3 a veces no soporta estos parámetros en ciertas versiones
        if "qwen" in model_id or "llama" in model_id:
            payload["repeat_penalty"] = 1.1
            payload["frequency_penalty"] = 0.3
            payload["presence_penalty"] = 0.2
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                LM_STUDIO_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    stats["llm_calls"] += 1
                    return data["choices"][0]["message"]["content"]
                else:
                    error_text = await response.text()
                    stats["errors"] += 1
                    print(f"   ❌ Error del LLM ({response.status}): {error_text[:200]}")
                    print(f"   Modelo activo: {model_id}")
                    print(f"   Payload enviado: {json.dumps({k: v for k, v in payload.items() if k != 'messages'})}")
                    return f"Error del LLM (status {response.status}): {error_text}"
                    
    except aiohttp.ClientError as e:
        stats["errors"] += 1
        print(f"   ❌ Error de conexión: {str(e)}")
        return f"Error de conexión con LM Studio: {str(e)}"
    except Exception as e:
        stats["errors"] += 1
        print(f"   ❌ Error inesperado: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Error inesperado: {str(e)}"


async def check_lm_studio_status():
    """
    Verifica si LM Studio está disponible
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:1234/v1/models",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return True, data
                return False, None
    except:
        return False, None


# ============================================================================
# FUNCIONES PARA IMÁGENES
# ============================================================================

async def download_image(file) -> bytes:
    """
    Descarga una imagen desde Telegram
    """
    try:
        # Descargar el archivo
        file_bytes = await file.download_as_bytearray()
        return bytes(file_bytes)
    except Exception as e:
        print(f"❌ Error descargando imagen: {e}")
        return None


def image_to_base64(image_bytes: bytes) -> str:
    """
    Convierte bytes de imagen a base64
    """
    return base64.b64encode(image_bytes).decode('utf-8')


# ============================================================================
# COMANDOS DEL BOT
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /start - Muestra mensaje de bienvenida sin borrar historial
    """
    # Verificar autorización
    if not await check_authorization(update):
        return
    
    user_id = update.effective_user.id
    
    # Cargar historial si no existe en memoria
    if user_id not in conversation_history:
        conversation_history[user_id] = load_conversation_history(user_id)
    
    welcome_message = (
        "¡Hola! 👋 Soy un bot conectado a un LLM local con capacidades de visión.\n\n"
        "Comandos disponibles:\n"
        "/help o /ayuda - Ver ayuda completa\n"
        "/stats - Ver estadísticas del sistema\n"
        "/clear - Limpiar historial de conversación\n"
        "/load - Cargar modelo en LM Studio\n"
        "/unload - Descargar modelo actual\n"
        "/exit o /salir - Cerrar el bot\n\n"
        "📸 Puedes enviarme imágenes y las analizaré\n"
        "💬 O simplemente escribe y charlemos\n"
        "🎲 Las preguntas aleatorias son generadas dinámicamente por el LLM\n"
        "💾 Tu historial se guarda automáticamente\n\n"
        "¡Envíame una imagen o escríbeme lo que quieras!"
    )
    
    await update.message.reply_text(welcome_message)
    stats["messages_sent"] += 1


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /stats - Muestra estadísticas del sistema
    """
    # Verificar autorización
    if not await check_authorization(update):
        return
    
    is_online, model_info = await check_lm_studio_status()
    
    uptime = datetime.now() - stats["start_time"]
    hours, remainder = divmod(uptime.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    status_emoji = "🟢" if is_online else "🔴"
    model_name = "Desconocido"
    
    if is_online and model_info and "data" in model_info and len(model_info["data"]) > 0:
        model_name = model_info["data"][0].get("id", "Desconocido")
    
    stats_message = (
        f"📊 **Estadísticas del Bot**\n\n"
        f"{status_emoji} **LM Studio**: {'Online' if is_online else 'Offline'}\n"
        f"🤖 **Modelo**: {model_name}\n\n"
        f"⏱️ **Tiempo activo**: {int(hours)}h {int(minutes)}m {int(seconds)}s\n"
        f"📨 **Mensajes recibidos**: {stats['messages_received']}\n"
        f"📸 **Imágenes recibidas**: {stats['images_received']}\n"
        f"📤 **Mensajes enviados**: {stats['messages_sent']}\n"
        f"🎲 **Mensajes aleatorios enviados**: {stats['random_messages_sent']}\n"
        f"⏭️ **Mensajes aleatorios omitidos**: {stats['random_messages_skipped']}\n"
        f"🔄 **Llamadas al LLM**: {stats['llm_calls']}\n"
        f"❌ **Errores**: {stats['errors']}\n"
    )
    
    await update.message.reply_text(stats_message, parse_mode='Markdown')
    stats["messages_sent"] += 1


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /clear - Limpia el historial de conversación (memoria y base de datos)
    """
    # Verificar autorización
    if not await check_authorization(update):
        return
    
    user_id = update.effective_user.id
    
    # Limpiar memoria
    conversation_history[user_id] = []
    
    # Limpiar base de datos
    deleted_count = clear_conversation_history_db(user_id)
    
    await update.message.reply_text(
        f"🧹 Historial de conversación limpiado.\n"
        f"📊 Eliminados {deleted_count} mensajes de la base de datos.\n"
        f"¡Empecemos de nuevo!"
    )
    stats["messages_sent"] += 1


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /help o /ayuda - Muestra información de ayuda
    """
    # Verificar autorización
    if not await check_authorization(update):
        return
    
    help_message = (
        "📚 *Ayuda del Bot*\n\n"
        "*Comandos disponibles:*\n"
        "/start - Mensaje de bienvenida\n"
        "/help o /ayuda - Esta ayuda\n"
        "/stats - Estadísticas del sistema\n"
        "/clear - Limpiar historial\n"
        "/load - Gestionar modelos\n"
        "/unload - Descargar modelo actual\n"
        "/exit o /salir - Cerrar el bot\n\n"
        "*Funcionalidades:*\n"
        "📸 Análisis de imágenes\n"
        "💬 Conversación con contexto\n"
        "🎲 Mensajes aleatorios\n"
        "💾 Historial persistente\n\n"
        "El bot usa LM Studio local. Usa /stats para ver el modelo activo."
    )
    
    await update.message.reply_text(help_message, parse_mode='Markdown')
    stats["messages_sent"] += 1


async def load_model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /load [nombre_modelo] - Carga un modelo en LM Studio
    Si no se especifica nombre, lista los modelos disponibles
    """
    # Verificar autorización
    if not await check_authorization(update):
        return
    
    # Obtener argumentos del comando (si los hay)
    model_name = " ".join(context.args) if context.args else None
    
    if not model_name:
        # Sin argumentos: listar modelos disponibles
        await update.message.reply_text("📋 Listando modelos disponibles...")
        
        try:
            import subprocess
            result = subprocess.run(
                ['lms', 'ls'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                models_output = result.stdout.strip()
                
                if models_output:
                    # Extraer solo los nombres de modelo
                    lines = models_output.split('\n')
                    models = []
                    for line in lines:
                        # Buscar líneas que parecen nombres de modelo
                        if '/' in line or line.strip():
                            parts = line.split()
                            if parts:
                                models.append(parts[0])
                    
                    if models:
                        models_list = "\n".join([f"• `{m}`" for m in models[:10]])  # Limitar a 10
                        await update.message.reply_text(
                            f"📦 **Modelos disponibles:**\n\n{models_list}\n\n"
                            f"💡 Usa `/load nombre_del_modelo` para cargarlo",
                            parse_mode='Markdown'
                        )
                    else:
                        await update.message.reply_text("❌ No se encontraron modelos descargados")
                else:
                    await update.message.reply_text("❌ No hay modelos disponibles")
            else:
                await update.message.reply_text(f"❌ Error al listar modelos:\n`{result.stderr[:200]}`", parse_mode='Markdown')
        
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    else:
        # Con argumentos: cargar el modelo especificado
        await update.message.reply_text(f"⏳ Cargando modelo `{model_name}`...", parse_mode='Markdown')
        
        try:
            import subprocess
            result = subprocess.run(
                ['lms', 'load', model_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                # Verificar si el modelo se cargó correctamente
                await asyncio.sleep(3)  # Dar tiempo para que cargue
                is_online, model_info = await check_lm_studio_status()
                
                if is_online and model_info and "data" in model_info and len(model_info["data"]) > 0:
                    loaded_model = model_info["data"][0].get("id", "Desconocido")
                    
                    # Hacer una prueba rápida con el modelo
                    test_msg = [{"role": "user", "content": "Di solo 'ok'"}]
                    test_response = await call_lm_studio(test_msg, max_tokens=10)
                    
                    if test_response.startswith("Error"):
                        await update.message.reply_text(
                            f"⚠️ Modelo cargado pero falla al responder:\n"
                            f"🤖 Modelo: `{loaded_model}`\n"
                            f"❌ Error: `{test_response[:150]}`\n\n"
                            f"Posibles causas:\n"
                            f"• System prompt incompatible\n"
                            f"• Modelo requiere parámetros específicos\n"
                            f"• Versión beta inestable",
                            parse_mode='Markdown'
                        )
                    else:
                        await update.message.reply_text(
                            f"✅ Modelo cargado y funcionando\n"
                            f"🤖 Modelo activo: `{loaded_model}`",
                            parse_mode='Markdown'
                        )
                else:
                    await update.message.reply_text(
                        "⚠️ Comando ejecutado, pero no se detecta modelo cargado.\n"
                        "Verifica LM Studio manualmente."
                    )
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                await update.message.reply_text(
                    f"❌ Error al cargar modelo:\n`{error_msg[:200]}`",
                    parse_mode='Markdown'
                )
        
        except subprocess.TimeoutExpired:
            await update.message.reply_text("⏱️ Tiempo de espera agotado. El modelo puede tardar en cargar.")
        except FileNotFoundError:
            await update.message.reply_text(
                "❌ Comando 'lms' no encontrado.\n"
                "Asegúrate de que LM Studio CLI esté instalado y en el PATH."
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    stats["messages_sent"] += 1


async def unload_model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /unload - Descarga el modelo actual de LM Studio
    """
    # Verificar autorización
    if not await check_authorization(update):
        return
    
    # Verificar qué modelo está cargado
    is_online, model_info = await check_lm_studio_status()
    
    if not is_online or not model_info or "data" not in model_info or len(model_info["data"]) == 0:
        await update.message.reply_text("ℹ️ No hay ningún modelo cargado actualmente")
        stats["messages_sent"] += 1
        return
    
    current_model = model_info["data"][0].get("id", "Desconocido")
    
    await update.message.reply_text(f"⏳ Descargando modelo `{current_model}`...", parse_mode='Markdown')
    
    try:
        import subprocess
        result = subprocess.run(
            ['lms', 'unload'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            # Verificar que se descargó
            await asyncio.sleep(1)
            is_online_after, _ = await check_lm_studio_status()
            
            if not is_online_after:
                await update.message.reply_text(
                    f"✅ Modelo descargado correctamente\n"
                    f"🔓 `{current_model}` ya no está en memoria",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("⚠️ El comando se ejecutó pero el modelo sigue cargado")
        else:
            error_msg = result.stderr if result.stderr else result.stdout
            await update.message.reply_text(
                f"❌ Error al descargar:\n`{error_msg[:200]}`",
                parse_mode='Markdown'
            )
    
    except subprocess.TimeoutExpired:
        await update.message.reply_text("⏱️ Tiempo de espera agotado")
    except FileNotFoundError:
        await update.message.reply_text(
            "❌ Comando 'lms' no encontrado.\n"
            "Asegúrate de que LM Studio CLI esté instalado."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    
    stats["messages_sent"] += 1


async def exit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /exit o /salir - Cierra el bot
    """
    # Verificar autorización
    if not await check_authorization(update):
        return
    
    await update.message.reply_text("👋 Cerrando el bot... ¡Hasta pronto!")
    stats["messages_sent"] += 1
    
    # Esperar un momento para que se envíe el mensaje
    await asyncio.sleep(1)
    
    # Detener la aplicación
    os._exit(0)


# ============================================================================
# MANEJADORES DE MENSAJES
# ============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Maneja los mensajes de texto del usuario
    """
    # Verificar autorización
    if not await check_authorization(update):
        return
    
    user_id = update.effective_user.id
    user_message = update.message.text
    
    stats["messages_received"] += 1
    
    # Inicializar historial si no existe, cargando desde BD
    if user_id not in conversation_history:
        conversation_history[user_id] = load_conversation_history(user_id)
    
    # Crear objeto de mensaje del usuario
    user_msg_obj = {
        "role": "user",
        "content": user_message
    }
    
    # Agregar mensaje del usuario al historial en memoria
    conversation_history[user_id].append(user_msg_obj)
    
    # Guardar mensaje del usuario en BD
    save_message_to_db(user_id, "user", user_msg_obj)
    
    # Obtener respuesta del LLM (usando el historial actual sin limitar aún)
    response = await call_lm_studio(conversation_history[user_id])
    
    # Crear objeto de mensaje del asistente
    assistant_msg_obj = {
        "role": "assistant",
        "content": response
    }
    
    # Agregar respuesta al historial en memoria
    conversation_history[user_id].append(assistant_msg_obj)
    
    # Guardar respuesta del asistente en BD
    save_message_to_db(user_id, "assistant", assistant_msg_obj)
    
    # Limitar el historial en memoria a los últimos 20 mensajes DESPUÉS de agregar todo
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]
    
    # Enviar respuesta al usuario
    await update.message.reply_text(response)
    stats["messages_sent"] += 1


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Maneja las imágenes enviadas por el usuario
    Compatible con Qwen3-VL y otros modelos de visión
    """
    # Verificar autorización
    if not await check_authorization(update):
        return
    
    user_id = update.effective_user.id
    stats["images_received"] += 1
    
    # Inicializar historial si no existe, cargando desde BD
    if user_id not in conversation_history:
        conversation_history[user_id] = load_conversation_history(user_id)
    
    # Obtener el caption (texto que acompaña la imagen) si existe
    caption = update.message.caption or "Describe esta imagen en detalle."
    
    print(f"\n📸 Imagen recibida (usuario: {user_id})")
    if update.message.caption:
        print(f"   Pregunta: {caption}")
    
    # Enviar mensaje de "procesando"
    processing_msg = await update.message.reply_text("🔍 Analizando la imagen...")
    
    try:
        # Obtener la imagen de mayor calidad disponible
        photo = update.message.photo[-1]
        
        # Descargar la imagen
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await download_image(file)
        
        if image_bytes is None:
            await processing_msg.edit_text("❌ Error al descargar la imagen. Por favor, intenta de nuevo.")
            stats["errors"] += 1
            return
        
        # Convertir a base64
        image_base64 = image_to_base64(image_bytes)
        
        # Crear mensaje multimodal para el LLM
        # IMPORTANTE: El orden es crítico para Qwen3-VL
        # Primero la imagen, luego el texto
        user_message = {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }
                },
                {
                    "type": "text",
                    "text": caption
                }
            ]
        }
        
        # Agregar al historial en memoria
        conversation_history[user_id].append(user_message)
        
        # Guardar en BD
        save_message_to_db(user_id, "user", user_message)
        
        # Obtener respuesta del LLM
        response = await call_lm_studio(conversation_history[user_id], max_tokens=1000)
        
        # Verificar si hay error en la respuesta
        if response.startswith("Error"):
            await processing_msg.edit_text(f"⚠️ {response}\n\nVerifica que LM Studio tenga un modelo de visión cargado (como Qwen3-VL).")
            stats["errors"] += 1
            return
        
        # Crear objeto de mensaje del asistente
        assistant_msg_obj = {
            "role": "assistant",
            "content": response
        }
        
        # Agregar respuesta al historial en memoria
        conversation_history[user_id].append(assistant_msg_obj)
        
        # Guardar respuesta en BD
        save_message_to_db(user_id, "assistant", assistant_msg_obj)
        
        # Limitar el historial en memoria DESPUÉS de agregar todo (imágenes ocupan más memoria)
        if len(conversation_history[user_id]) > 10:
            conversation_history[user_id] = conversation_history[user_id][-10:]
        
        # Editar el mensaje de "procesando" con la respuesta
        await processing_msg.edit_text(f"📸 **Análisis de imagen:**\n\n{response}", parse_mode='Markdown')
        stats["messages_sent"] += 1
        
        print(f"   ✅ Imagen procesada y respuesta enviada\n")
        
    except Exception as e:
        print(f"   ❌ Error procesando imagen: {str(e)}")
        await processing_msg.edit_text(
            f"❌ Error al procesar la imagen.\n\n"
            f"Verifica que LM Studio esté ejecutándose con un modelo de visión cargado."
        )
        stats["errors"] += 1


# ============================================================================
# MENSAJES ALEATORIOS
# ============================================================================

async def generate_random_question():
    """
    Genera una pregunta aleatoria usando el LLM
    Devuelve una pregunta única y natural cada vez
    """
    prompt = """Genera una pregunta interesante y natural para iniciar una conversación casual y cercana.

La pregunta puede ser sobre alguno de estos temas:
- Astronomía
- Cultura
- Inteligencia artificial
- Creatividad e ideas innovadoras
- Programación
- Curiosidades del mundo

Requisitos:
- Que sea cálida y cercana, como si la hiciera una amiga
- Puede incluir un emoji si lo ves apropiado
- Debe invitar a una respuesta reflexiva, no solo sí/no
- Máximo 3 líneas de texto

Devuelve SOLO la pregunta, sin explicaciones, sin comillas, sin introducción."""

    try:
        question = await call_lm_studio([{"role": "user", "content": prompt}], max_tokens=150)
        # Limpiar la respuesta de posibles comillas o texto extra
        question = question.strip().strip('"').strip("'")
        return question
    except Exception as e:
        print(f"❌ Error generando pregunta aleatoria: {e}")
        # Fallback a una pregunta genérica si falla
        return "¿Cómo te sientes hoy? Cuéntame qué hay en tu mente"


async def send_random_messages(application):
    """
    Envía mensajes aleatorios de vez en cuando para dar naturalidad
    Ahora el LLM genera las preguntas dinámicamente
    Solo envía al usuario autorizado
    """
    print("🎲 Sistema de mensajes aleatorios activado (modo: preguntas generadas por LLM)")
    
    while True:
        try:
            # Esperar un tiempo aleatorio
            wait_time = random.randint(MIN_RANDOM_MESSAGE_INTERVAL, MAX_RANDOM_MESSAGE_INTERVAL)
            print(f"⏰ Esperando {wait_time//60} minutos para el próximo mensaje aleatorio...")
            await asyncio.sleep(wait_time)
            
            print(f"🎲 Evaluando si enviar mensaje aleatorio...")
            
            # Decidir si enviar mensaje basado en probabilidad
            if random.random() > RANDOM_MESSAGE_PROBABILITY:
                stats["random_messages_skipped"] += 1
                print(f"⏭️  Mensaje aleatorio omitido por probabilidad (total omitidos: {stats['random_messages_skipped']})")
                continue
            
            # Generar una pregunta aleatoria con el LLM
            print("🤖 Generando pregunta aleatoria con LLM...")
            question = await generate_random_question()
            print(f"❓ Pregunta generada: {question}")
            
            # Obtener respuesta del LLM a esa pregunta
            print("💭 Generando respuesta...")
            messages = [{"role": "user", "content": question}]
            response = await call_lm_studio(messages, max_tokens=500)
            
            # Enviar el mensaje solo al usuario autorizado
            # Formato: Primero la pregunta, luego la respuesta
            message_text = (
                f"💭 *Pensamiento aleatorio:*\n\n"
                f"❓ _{question}_\n\n"
                f"{response}"
            )
            
            await application.bot.send_message(
                chat_id=AUTHORIZED_USER_ID,
                text=message_text,
                parse_mode='Markdown'
            )
            
            stats["messages_sent"] += 1
            stats["random_messages_sent"] += 1
            print(f"📤 Mensaje aleatorio enviado al usuario {AUTHORIZED_USER_ID}")
            print(f"   Total mensajes aleatorios enviados: {stats['random_messages_sent']}")
            print(f"   Próximo mensaje en {wait_time//60} minutos aproximadamente")
            
        except Exception as e:
            print(f"❌ Error en mensajes aleatorios: {e}")
            print(f"   Tipo de error: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            await asyncio.sleep(60)


# ============================================================================
# FUNCIÓN PRINCIPAL
# ============================================================================

async def main():
    """
    Función principal del bot
    """
    print("🤖 Iniciando bot de Telegram con LM Studio (con capacidades de visión)...")
    
    # Inicializar base de datos
    init_database()
    
    # Verificar que LM Studio está disponible
    is_online, _ = await check_lm_studio_status()
    if not is_online:
        print("⚠️  ADVERTENCIA: LM Studio no está disponible en http://localhost:1234")
        print("   Asegúrate de que LM Studio esté ejecutándose y el servidor local esté activo")
    else:
        print("✅ LM Studio conectado correctamente")
    
    # Crear la aplicación
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Registrar comandos
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ayuda", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("load", load_model_command))
    application.add_handler(CommandHandler("unload", unload_model_command))
    application.add_handler(CommandHandler("exit", exit_command))
    application.add_handler(CommandHandler("salir", exit_command))
    
    # CRÍTICO: El orden importa - fotos ANTES que texto
    # Si el handler de texto va primero, puede capturar el caption de las fotos
    # y la foto nunca llegará a handle_photo
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Iniciar el bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    print("✅ Bot iniciado correctamente")
    print("📱 Escuchando mensajes de Telegram...")
    print("📸 Soporte para imágenes activado")
    print("🎲 Mensajes aleatorios habilitados")
    print("\n💡 Presiona Ctrl+C para detener el bot o usa /exit en Telegram\n")
    
    # Iniciar tarea de mensajes aleatorios en segundo plano
    asyncio.create_task(send_random_messages(application))
    
    # Mantener el bot ejecutándose
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\n\n👋 Deteniendo el bot...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        print("✅ Bot detenido correctamente")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot cerrado por el usuario")
        sys.exit(0)

# Chatobot

Bot de Telegram conectado a LM Studio local con soporte para visión (Qwen/VL).

Resumen
- Proyecto en Python 3.10+
- Usa `python-telegram-bot` y `aiohttp` para comunicarse con Telegram y LM Studio
- Historial persistente con SQLite (`chatobot.db`)

Requisitos
- Python 3.10 o superior
- LM Studio corriendo localmente en `http://localhost:1234`

Instalación rápida
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Variables de entorno necesarias
- `TELEGRAM_TOKEN` — token de tu bot de Telegram
- `ALLOWED_USER_ID` — ID numérico del usuario autorizado
- `SYSTEM_PROMPT` — prompt de sistema para el LLM

Ejecutar el bot (modo local)
```bash
export TELEGRAM_TOKEN="<tu-token>"
export ALLOWED_USER_ID="<tu-id>"
export SYSTEM_PROMPT="<tu-system-prompt>"
python chatobot.py
```

Preparar para subir a GitHub (ejemplo)
```bash
git init
git add .
git commit -m "Initial commit"
# Ajusta la URL remota con tu usuario/repositorio
git branch -M main
git remote add origin git@github.com:TU_USUARIO/chatbot.git
git push -u origin main
```

Notas
- `test_qwen_vision.py` crea una imagen de prueba con Pillow (opcional) para verificar capacidades de visión.
- No incluyo el token ni el DB en el repo; usa `.env` o GitHub Secrets para CI.

Contribuir
- Abre issues o pull requests en el repo remoto.


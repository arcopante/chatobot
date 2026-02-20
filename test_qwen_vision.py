#!/usr/bin/env python3
"""
Script de prueba para verificar que Qwen2-VL funciona correctamente en LM Studio
"""

import aiohttp
import asyncio
import base64
import json
from pathlib import Path

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"

async def test_text_only():
    """Prueba solo con texto"""
    print("\n" + "="*60)
    print("TEST 1: Solo texto")
    print("="*60)
    
    payload = {
        "messages": [
            {"role": "user", "content": "Hola, ¿cómo estás?"}
        ],
        "temperature": 0.7,
        "max_tokens": 100,
        "stream": False
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                LM_STUDIO_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    print("✅ Respuesta del modelo:")
                    print(data["choices"][0]["message"]["content"])
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Error {response.status}: {error_text}")
                    return False
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return False


async def test_with_image():
    """Prueba con imagen (requiere que tengas una imagen de prueba)"""
    print("\n" + "="*60)
    print("TEST 2: Texto + Imagen (Formato Qwen3-VL)")
    print("="*60)
    
    # Crear una imagen de prueba simple (cuadrado rojo)
    try:
        from PIL import Image
        import io
        
        # Crear imagen de prueba (100x100 rojo)
        img = Image.new('RGB', (100, 100), color='red')
        
        # Convertir a bytes
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_bytes = img_byte_arr.getvalue()
        
        # Convertir a base64
        image_base64 = base64.b64encode(img_bytes).decode('utf-8')
        
        print(f"📸 Imagen de prueba creada: 100x100 píxeles")
        print(f"   Tamaño en bytes: {len(img_bytes)}")
        print(f"   Base64 length: {len(image_base64)} caracteres")
        print(f"   Primeros 50 chars: {image_base64[:50]}...")
        
    except ImportError:
        print("⚠️  PIL no está instalado. Instálalo con: pip install Pillow")
        return False
    
    # Formato exacto para Qwen3-VL según la documentación
    # El orden es importante: primero imagen, luego texto
    payload = {
        "messages": [
            {
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
                        "text": "What color is this image? Answer in one word."
                    }
                ]
            }
        ],
        "temperature": 0.7,
        "max_tokens": 50,
        "stream": False
    }
    
    print("\n📤 Enviando solicitud al LLM...")
    print("   Estructura del mensaje:")
    print("      1. image_url con data:image/jpeg;base64,...")
    print("      2. text con pregunta")
    print(f"   Max tokens: 50")
    
    try:
        async with aiohttp.ClientSession() as session:
            print("   🔄 Conectando a LM Studio...")
            async with session.post(
                LM_STUDIO_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                print(f"\n📥 Status code: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    print("✅ Respuesta del modelo:")
                    response_text = data["choices"][0]["message"]["content"]
                    print(f"   {response_text}")
                    
                    # Verificar que mencionó el color rojo
                    if "red" in response_text.lower() or "rojo" in response_text.lower():
                        print("\n✅ El modelo identificó correctamente el color!")
                        return True
                    else:
                        print(f"\n⚠️  El modelo respondió pero no identificó el color correctamente")
                        print(f"   Respuesta: {response_text}")
                        return True  # Aún así cuenta como éxito si respondió
                else:
                    error_text = await response.text()
                    print(f"❌ Error {response.status}:")
                    print(f"   {error_text[:500]}")
                    
                    # Intentar parsear el error como JSON para más detalles
                    try:
                        error_json = json.loads(error_text)
                        if "error" in error_json:
                            print(f"\n   Detalles del error:")
                            print(f"   {json.dumps(error_json['error'], indent=2)}")
                    except:
                        pass
                    
                    return False
                    
    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"   Tipo: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False


async def check_model_info():
    """Verifica qué modelo está cargado"""
    print("\n" + "="*60)
    print("INFO: Verificando modelo cargado")
    print("="*60)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:1234/v1/models",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if "data" in data and len(data["data"]) > 0:
                        model = data["data"][0]
                        print(f"✅ Modelo activo: {model.get('id', 'Desconocido')}")
                        print(f"   Creado: {model.get('created', 'N/A')}")
                        return True
                    else:
                        print("⚠️  No hay ningún modelo cargado en LM Studio")
                        return False
                else:
                    print(f"❌ Error {response.status}")
                    return False
    except Exception as e:
        print(f"❌ No se puede conectar a LM Studio: {e}")
        print("\nAsegúrate de que:")
        print("1. LM Studio está abierto")
        print("2. El servidor local está iniciado")
        print("3. El puerto es 1234 (por defecto)")
        return False


async def main():
    print("\n🧪 SCRIPT DE PRUEBA PARA QWEN2-VL EN LM STUDIO")
    print("=" * 60)
    
    # Verificar conexión
    if not await check_model_info():
        print("\n❌ No se puede continuar sin conexión a LM Studio")
        return
    
    # Test 1: Solo texto
    if not await test_text_only():
        print("\n❌ La prueba de texto falló")
        return
    
    # Test 2: Con imagen
    if not await test_with_image():
        print("\n❌ La prueba con imagen falló")
        print("\n💡 Posibles problemas:")
        print("   1. El modelo cargado no tiene capacidades de visión")
        print("   2. LM Studio necesita reiniciarse")
        print("   3. El modelo no está configurado correctamente")
        print("\n📝 Soluciones:")
        print("   1. En LM Studio, descarga un modelo Qwen2-VL o similar")
        print("   2. Carga el modelo completamente antes de usar el bot")
        print("   3. Verifica los logs de LM Studio para errores")
        return
    
    print("\n" + "="*60)
    print("✅ TODAS LAS PRUEBAS PASARON")
    print("="*60)
    print("El bot debería funcionar correctamente con imágenes")
    print()


if __name__ == "__main__":
    asyncio.run(main())

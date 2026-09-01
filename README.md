# Discord Music Bot - Python

## Características
- ✅ Comandos slash (/play, /skip, /stop, /queue, /nowplaying, /volume, /leave, /musichelp)
- ✅ Panel de control interactivo estilo YouTube Music
- ✅ Sistema de cola por servidor con indicadores de progreso
- ✅ Soporte para nombres de canciones y links de YouTube
- ✅ Embeds profesionales con barra de progreso en tiempo real
- ✅ **Ecualizador profesional de 10 bandas**
- ✅ **8 presets de equalizador (Flat, Bass Boost, Rock, Pop, Vocal, Electronic, Night Mode, Custom Bass)**
- ✅ **Ajuste manual de las 10 bandas de frecuencia**
- ✅ Panel que se actualiza automáticamente
- ✅ Bot se mueve inteligentemente entre canales del mismo servidor
- ✅ Manejo de errores claro

## Configuración en SparkedHost/Pterodactyl

### Archivos del servidor:
1. Conecta el repositorio: `fh4xdzzz/BOT-MUSIC`
2. Selección la rama: `master`

### Comando de inicio:
- Configura `${STARTUP_FILE}` = `main.py`

### Variables de entorno:
En la sección de "Variables" configura:
- `DISCORD_TOKEN` = tu token de Discord

## Comandos slash:
- `/play [canción]` - Reproducir una canción
- `/skip` - Saltar canción actual
- `/stop` - Detener música y limpiar cola
- `/queue` - Ver cola de reproducción
- `/nowplaying` - Canción actual con panel actualizado
- `/volume [0-100]` - Cambiar volumen
- `/leave` - Desconectar del canal de voz
- `/musichelp` - Mostrar todos los comandos disponibles

## Panel de control YouTube Music:
El bot muestra un panel completo con:
- ⏸️/▶️ Pausar/Reanudar (con indicador visual)
- ⏭️ Skip
- ⏹️ Stop
- 🔁 Loop (repetir canción actual)
- � Reiniciar canción
- �📜 Ver cola completa
- 🔀 Mezclar cola
- 🎚️ Volumen actual
- 🎛️ **Ecualizador profesional**
- ❤️ Marcar como favorita

## Ecualizador Profesional:
Sistema de equalizador de 10 bandas con rango de -12dB a +12dB:
- **Bandas de frecuencia:** 31Hz, 62Hz, 125Hz, 250Hz, 500Hz, 1kHz, 2kHz, 4kHz, 8kHz, 16kHz
- **Presets disponibles:**
  - 🔘 **Flat** - Sin ecualización (default)
  - 🔊 **Bass Boost** - Enfatiza bajos
  - 🎸 **Rock** - Para música rock
  - 🎤 **Pop** - Para música pop
  - 🎙️ **Vocal** - Enfatiza voces
  - 🎹 **Electronic** - Para música electrónica
  - 🌙 **Night Mode** - Para escuchar de noche
  - 🎛️ **Custom Bass** - Configuración personalizada (+12dB graves, +4dB presencia)
- **Personalización:** Ajuste manual de las 10 bandas en dos grupos (1-5 y 6-10)
- **Bypass:** Desactivación del ecualizador sin perder la configuración

## Requisitos:
- Python 3.12+
- FFmpeg (incluido en SparkedHost)
- Bibliotecas de audio (incluidas en SparkedHost)
- davey>=0.1.0 (para compatibilidad de voz)

## Notas:
- Este bot usa Python y discord.py
- Optimizado para funcionar en SparkedHost/Pterodactyl
- La interfaz es estilo YouTube Music con progreso en tiempo real
- El bot cambia automáticamente entre canales del mismo servidor
- El ecualizador usa filtros FFmpeg profesionales de 10 bandas
- Los cambios de equalizador se aplican reiniciando el stream actual

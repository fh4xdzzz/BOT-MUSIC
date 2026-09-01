# Discord Music Bot - Python

## Características
- ✅ Comandos slash (/play, /skip, /stop, /queue, /nowplaying, /pause, /resume, /volume, /equalizer, /leave)
- ✅ Panel de control interactivo estilo YouTube Music
- ✅ Sistema de cola por servidor con indicadores de progreso
- ✅ Soporte para nombres de canciones y links de YouTube
- ✅ Embeds profesionales con barra de progreso en tiempo real
- ✅ Sistema de equalizador con 5 presets (flat, bass, treble, boost, vocal)
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
- `/pause` - Pausar música
- `/resume` - Reanudar música
- `/volume [1-100]` - Cambiar volumen
- `/equalizer [preset]` - Cambiar equalizador (flat, bass, treble, boost, vocal)
- `/leave` - Desconectar del canal de voz
- `/musichelp` - Mostrar todos los comandos disponibles

## Panel de control YouTube Music:
El bot muestra un panel completo con:
- ⏸️/▶️ Pausar/Reanudar (con indicador visual)
- ⏭️ Skip
- ⏹️ Stop
- � Loop (repetir canción actual)
- �📜 Ver cola completa
- 🎚️ Equalizer presets
- ➕ Añadir pista (hint)
- 🔀 Mezclar cola
- ❤️ Marcar como favorita

## Equalizer presets:
- 🔘 **Flat** - Sin ecualización (default)
- 🔊 **Bass** - Bajos más fuertes
- 🔔 **Treble** - Agudos más fuertes  
- 🚀 **Boost** - Mejora general de audio
- 🎙 **Vocal** - Ecualizador simple

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
- Si hay problemas de audio, contacta al soporte del hosting

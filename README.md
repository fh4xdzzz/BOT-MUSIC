# Discord Music Bot - Python

## Características
- Comandos slash (/play, /skip, /stop, /queue, /nowplaying, /pause, /resume, /volume)
- Panel de control interactivo con botones
- Sistema de cola por servidor
- Soporte para nombres de canciones y links de YouTube
- Embeds profesionales
- Manejo de errores claro

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
- `/nowplaying` - Canción actual
- `/pause` - Pausar música
- `/resume` - Reanudar música
- `/volume [1-100]` - Cambiar volumen

## Panel de control:
El bot muestra un panel con botones al reproducir:
- ⏸️/▶️ Pausar/Reanudar
- ⏭️ Skip
- ⏹️ Stop
- 📜 Ver cola

## Requisitos:
- Python 3.12+
- FFmpeg (incluido en SparkedHost)
- Bibliotecas de audio (incluidas en SparkedHost)

## Notas:
- Este bot usa Python y discord.py
- Optimizado para funcionar en SparkedHost/Pterodactyl
- Si hay problemas de audio, contacta al soporte del hosting

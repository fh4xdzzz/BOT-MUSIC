# JMusicBot Setup Guide

## Paso 1: Descargar JMusicBot
1. Ve a https://jmusicbot.com/
2. Descarga la versión más reciente del JAR (normalmente algo como "JMusicBot-0.x.x.jar")
3. Guarda el archivo JAR en esta carpeta

## Paso 2: Configurar en SparkedHost/Pterodactyl

### Archivos del servidor:
1. Entra al panel de tu servidor en SparkedHost
2. Ve a la sección "Archivos" o "Files"
3. Sube el archivo JAR descargado (ej: JMusicBot-0.x.x.jar)

### Comando de inicio:
- Configura el comando de inicio como: `java -jar JMusicBot-0.x.x.jar`
- (Reemplaza JMusicBot-0.x.x.jar con el nombre exacto del archivo que descargaste)

### Variables de entorno:
En la sección de "Variables" configura:
- `DISCORD BOT TOKEN` = tu token de Discord
- `BOT OWNER ID` = tu ID de usuario de Discord (ej: 796931424112476171)
- `BOT PREFIX` = @mention (o el prefijo que prefieras, como !)

## Paso 3: Iniciar el servidor
1. Guarda todos los cambios
2. Inicia el servidor desde el panel
3. El bot debería conectarse a Discord automáticamente

## Comandos básicos de JMusicBot:
- `@BotName play [canción]` - Reproducir una canción
- `@BotName skip` - Saltar canción actual
- `@BotName stop` - Detener música
- `@BotName queue` - Ver cola
- `@BotName np` - Canción actual
- `@BotName volume [1-100]` - Cambiar volumen

## Notas importantes:
- JMusicBot usa Java, no Python
- No requiere FFmpeg ni bibliotecas adicionales
- Funciona perfectamente en la mayoría de hostings
- Los archivos del repositorio anterior ya fueron eliminados

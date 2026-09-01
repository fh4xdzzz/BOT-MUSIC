import os
import asyncio
import yt_dlp
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View
import nacl
from typing import Optional
from dotenv import load_dotenv

# Cargar variables de entorno desde archivo .env si existe
load_dotenv()

# Configuración
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Estructura de datos para colas por servidor
queues = {}
current_tracks = {}

# Configuración de yt-dlp
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtoscreen': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn -b:a 128k -ar 48000',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -probesize 32 -analyzeduration 0'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.FFmpegOpusAudio):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, **ffmpeg_options)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.uploader = data.get('uploader')
        self.webpage_url = data.get('webpage_url')
        self.volume = volume

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            data = data['entries'][0]
        
        try:
            source = discord.FFmpegPCMAudio(filename if not stream else data['url'], **ffmpeg_options)
        except Exception as e:
            print(f"Error creando FFmpegPCMAudio: {e}")
            raise
        
        return cls(source, data=data)

class MusicControlView(View):
    def __init__(self, guild_id: int, timeout=None):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id

    @discord.ui.button(label="⏸️", style=discord.ButtonStyle.secondary, emoji="⏸️")
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        voice_client = interaction.guild.voice_client
        
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            button.label = "▶️"
            button.emoji = "▶️"
            await interaction.response.edit_message(view=self)
        elif voice_client and voice_client.is_paused():
            voice_client.resume()
            button.label = "⏸️"
            button.emoji = "⏸️"
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message("No hay música reproduciéndose.", ephemeral=True)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        voice_client = interaction.guild.voice_client
        
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await interaction.response.send_message("⏭️ Canción saltada.", ephemeral=True)
        else:
            await interaction.response.send_message("No hay música para saltar.", ephemeral=True)

    @discord.ui.button(label="⏹️", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        voice_client = interaction.guild.voice_client
        
        if voice_client:
            queues[guild_id] = []
            current_tracks[guild_id] = None
            voice_client.stop()
            await voice_client.disconnect()
            await interaction.response.edit_message(content="⏹️ Música detenida y desconectado.", view=None)
        else:
            await interaction.response.send_message("No estoy en un canal de voz.", ephemeral=True)

    @discord.ui.button(label="📜", style=discord.ButtonStyle.secondary, emoji="📜")
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        queue = queues.get(guild_id, [])
        
        if not queue:
            await interaction.response.send_message("La cola está vacía.", ephemeral=True)
            return
        
        queue_list = "\n".join([f"{i+1}. {track['title']}" for i, track in enumerate(queue[:10])])
        if len(queue) > 10:
            queue_list += f"\n... y {len(queue) - 10} más"
        
        embed = discord.Embed(
            title="📜 Cola de reproducción",
            description=queue_list,
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Total: {len(queue)} canciones")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def play_next(guild_id: int, voice_client: discord.VoiceClient, interaction: Optional[discord.Interaction] = None):
    queue = queues.get(guild_id, [])
    
    if not queue:
        current_tracks[guild_id] = None
        if voice_client and not voice_client.is_playing():
            await voice_client.disconnect()
        return
    
    track = queue.pop(0)
    current_tracks[guild_id] = track
    
    try:
        player = await YTDLSource.from_url(track['url'], loop=bot.loop, stream=True)
        voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(
            play_next(guild_id, voice_client), bot.loop
        ))
        
        # Crear embed con información de la canción
        embed = discord.Embed(
            title="🎵 Reproduciendo ahora",
            description=f"**{player.title}**",
            color=discord.Color.green()
        )
        embed.add_field(name="Duración", value=f"{player.duration // 60}:{player.duration % 60:02d}", inline=True)
        embed.add_field(name="Subido por", value=player.uploader, inline=True)
        embed.set_thumbnail(url=player.thumbnail)
        embed.set_footer(text=f"Solicitado por {track['requester']}")
        
        view = MusicControlView(guild_id, timeout=None)
        
        if interaction:
            await interaction.followup.send(embed=embed, view=view)
        else:
            # Enviar al canal de texto donde está el bot
            channel = bot.get_channel(track['channel_id'])
            if channel:
                await channel.send(embed=embed, view=view)
                
    except Exception as e:
        print(f"Error reproduciendo: {e}")
        await play_next(guild_id, voice_client)

@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user.name}")
    try:
        synced = await bot.tree.sync()
        print(f"Comandos sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Error sincronizando comandos: {e}")

@bot.tree.command(name="play", description="Reproduce una canción de YouTube")
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    
    if not interaction.user.voice:
        await interaction.followup.send("❌ Debes estar en un canal de voz.", ephemeral=True)
        return
    
    voice_channel = interaction.user.voice.channel
    guild_id = interaction.guild.id
    
    # Conectar al canal de voz si no está conectado
    voice_client = interaction.guild.voice_client
    if not voice_client:
        try:
            print(f"Intentando conectar al canal {voice_channel.name}...")
            voice_client = await voice_channel.connect(self_deaf=True)
            print(f"Conectado exitosamente al canal {voice_channel.name}")
        except Exception as e:
            print(f"Error detallado al conectar: {type(e).__name__}: {e}")
            error_msg = str(e).lower()
            if "libav" in error_msg or "ffmpeg" in error_msg:
                await interaction.followup.send("❌ Error: El servidor no tiene FFmpeg instalado correctamente. Contacta al administrador del hosting.", ephemeral=True)
            elif "opus" in error_msg or "davey" in error_msg:
                await interaction.followup.send("❌ Error: Bibliotecas de audio faltantes. Contacta al administrador del hosting.", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Error al conectar al canal de voz: {e}", ephemeral=True)
            return
    
    # Buscar la canción
    try:
        info = await asyncio.to_thread(ytdl.extract_info, query, download=False)
        
        if 'entries' in info:
            info = info['entries'][0]
        
        track = {
            'title': info['title'],
            'url': info['webpage_url'],
            'duration': info['duration'],
            'thumbnail': info['thumbnail'],
            'uploader': info['uploader'],
            'requester': interaction.user.display_name,
            'channel_id': interaction.channel.id
        }
        
        # Añadir a la cola
        if guild_id not in queues:
            queues[guild_id] = []
        
        queues[guild_id].append(track)
        
        # Si no está reproduciendo, empezar
        if not voice_client.is_playing() and not voice_client.is_paused():
            await play_next(guild_id, voice_client, interaction)
        else:
            embed = discord.Embed(
                title="✅ Añadido a la cola",
                description=f"**{track['title']}**",
                color=discord.Color.blue()
            )
            embed.add_field(name="Duración", value=f"{track['duration'] // 60}:{track['duration'] % 60:02d}", inline=True)
            embed.set_thumbnail(url=track['thumbnail'])
            embed.set_footer(text=f"Posición en cola: {len(queues[guild_id])}")
            await interaction.followup.send(embed=embed)
            
    except Exception as e:
        await interaction.followup.send(f"❌ Error al buscar la canción: {e}", ephemeral=True)

@bot.tree.command(name="skip", description="Salta la canción actual")
async def skip(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("❌ No hay música reproduciéndose.", ephemeral=True)
        return
    
    voice_client.stop()
    await interaction.response.send_message("⏭️ Canción saltada.")

@bot.tree.command(name="stop", description="Detiene la música y limpia la cola")
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    guild_id = interaction.guild.id
    
    if not voice_client:
        await interaction.response.send_message("❌ No estoy en un canal de voz.", ephemeral=True)
        return
    
    queues[guild_id] = []
    current_tracks[guild_id] = None
    voice_client.stop()
    await voice_client.disconnect()
    
    await interaction.response.send_message("⏹️ Música detenida y desconectado.")

@bot.tree.command(name="queue", description="Muestra la cola de reproducción")
async def queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    queue = queues.get(guild_id, [])
    
    if not queue:
        await interaction.response.send_message("❌ La cola está vacía.", ephemeral=True)
        return
    
    queue_list = "\n".join([f"{i+1}. {track['title']}" for i, track in enumerate(queue[:15])])
    if len(queue) > 15:
        queue_list += f"\n... y {len(queue) - 15} más"
    
    embed = discord.Embed(
        title="📜 Cola de reproducción",
        description=queue_list,
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Total: {len(queue)} canciones")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="nowplaying", description="Muestra la canción actual")
async def nowplaying(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    track = current_tracks.get(guild_id)
    voice_client = interaction.guild.voice_client
    
    if not track or not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("❌ No hay música reproduciéndose.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🎵 Reproduciendo ahora",
        description=f"**{track['title']}**",
        color=discord.Color.green()
    )
    embed.add_field(name="Duración", value=f"{track['duration'] // 60}:{track['duration'] % 60:02d}", inline=True)
    embed.add_field(name="Subido por", value=track['uploader'], inline=True)
    embed.set_thumbnail(url=track['thumbnail'])
    embed.set_footer(text=f"Solicitado por {track['requester']}")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pause", description="Pausa la música")
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("❌ No hay música reproduciéndose.", ephemeral=True)
        return
    
    voice_client.pause()
    await interaction.response.send_message("⏸️ Música pausada.")

@bot.tree.command(name="resume", description="Reanuda la música")
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_paused():
        await interaction.response.send_message("❌ No hay música pausada.", ephemeral=True)
        return
    
    voice_client.resume()
    await interaction.response.send_message("▶️ Música reanudada.")

@bot.tree.command(name="volume", description="Cambia el volumen (1-100)")
async def volume(interaction: discord.Interaction, volume: int):
    if volume < 1 or volume > 100:
        await interaction.response.send_message("❌ El volumen debe estar entre 1 y 100.", ephemeral=True)
        return
    
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("❌ No hay música reproduciéndose.", ephemeral=True)
        return
    
    voice_client.source.volume = volume / 100
    await interaction.response.send_message(f"🔊 Volumen establecido al {volume}%")

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("Error: DISCORD_TOKEN no está configurado en las variables de entorno.")
    else:
        bot.run(token)

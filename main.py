import os
import asyncio
import discord
import yt_dlp

from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button

# ============================================================
# CONFIGURACIÓN
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "No se encontró DISCORD_TOKEN. Configúrala en las variables de entorno de SparkedHost."
    )

# FFmpeg debe estar instalado en el servidor.
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

YTDLP_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "source_address": "0.0.0.0",
}

intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
)

# Un reproductor/cola independiente por servidor.
music_players = {}


class Track:
    def __init__(self, title, url, webpage_url, duration=0):
        self.title = title
        self.url = url
        self.webpage_url = webpage_url
        self.duration = duration or 0


class GuildMusic:
    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.queue = []
        self.current = None
        self.voice = None
        self.volume = 0.5
        self.lock = asyncio.Lock()

    async def play_next(self):
        async with self.lock:
            if not self.queue:
                self.current = None
                return

            track = self.queue.pop(0)
            self.current = track

            if not self.voice or not self.voice.is_connected():
                self.current = None
                return

            source = discord.FFmpegPCMAudio(
                track.url,
                **FFMPEG_OPTIONS
            )
            source = discord.PCMVolumeTransformer(source, volume=self.volume)

            def after(error):
                if error:
                    print(f"[Guild {self.guild_id}] Error de reproducción: {error}")
                asyncio.run_coroutine_threadsafe(
                    self.play_next(),
                    bot.loop
                )

            self.voice.play(source, after=after)

            print(f"[Guild {self.guild_id}] Reproduciendo: {track.title}")


def get_player(guild_id):
    if guild_id not in music_players:
        music_players[guild_id] = GuildMusic(guild_id)
    return music_players[guild_id]


async def extract_track(query):
    loop = asyncio.get_running_loop()

    def extract():
        with yt_dlp.YoutubeDL(YTDLP_OPTIONS) as ydl:
            info = ydl.extract_info(query, download=False)

            if "entries" in info:
                entries = [entry for entry in info["entries"] if entry]
                if not entries:
                    raise ValueError("No encontré resultados.")
                info = entries[0]

            return Track(
                title=info.get("title", "Canción desconocida"),
                url=info["url"],
                webpage_url=info.get("webpage_url", query),
                duration=info.get("duration", 0),
            )

    return await loop.run_in_executor(None, extract)


def format_duration(seconds):
    if not seconds:
        return "?:??"

    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    return f"{minutes}:{seconds:02d}"


class MusicControls(View):
    def __init__(self, player):
        super().__init__(timeout=None)
        self.player = player

    @discord.ui.button(label="⏯️ Pausar/Reanudar", style=discord.ButtonStyle.primary)
    async def pause_resume(self, interaction: discord.Interaction, button: Button):
        voice = self.player.voice

        if not voice or not voice.is_connected():
            await interaction.response.send_message(
                "❌ El bot no está conectado a un canal de voz.",
                ephemeral=True
            )
            return

        if voice.is_playing():
            voice.pause()
            await interaction.response.send_message("⏸️ Música pausada.", ephemeral=True)

        elif voice.is_paused():
            voice.resume()
            await interaction.response.send_message("▶️ Música reanudada.", ephemeral=True)

        else:
            await interaction.response.send_message(
                "❌ No hay una canción reproduciéndose.",
                ephemeral=True
            )

    @discord.ui.button(label="⏭️ Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: Button):
        voice = self.player.voice

        if not voice or not voice.is_playing():
            await interaction.response.send_message(
                "❌ No hay una canción reproduciéndose.",
                ephemeral=True
            )
            return

        voice.stop()
        await interaction.response.send_message("⏭️ Canción saltada.", ephemeral=True)

    @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: Button):
        voice = self.player.voice

        self.player.queue.clear()
        self.player.current = None

        if voice and voice.is_connected():
            voice.stop()

        await interaction.response.send_message(
            "⏹️ Reproducción detenida y cola limpiada.",
            ephemeral=True
        )


# ============================================================
# EVENTOS
# ============================================================

@bot.event
async def on_ready():
    print("==========================================")
    print(f"✅ Bot conectado: {bot.user}")
    print(f"🆔 ID: {bot.user.id}")
    print(f"🌐 Servidores: {len(bot.guilds)}")
    print("==========================================")

    try:
        synced = await bot.tree.sync()
        print(f"✅ Slash commands sincronizados: {len(synced)}")
    except Exception as error:
        print(f"❌ Error sincronizando comandos: {error}")


@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id and before.channel and not after.channel:
        player = music_players.get(member.guild.id)
        if player:
            player.voice = None
            player.current = None


# ============================================================
# /PLAY
# ============================================================

@bot.tree.command(
    name="play",
    description="Reproduce una canción por nombre o enlace."
)
@app_commands.describe(
    query="Nombre de la canción o enlace de YouTube"
)
async def play(interaction: discord.Interaction, query: str):

    if not interaction.guild:
        await interaction.response.send_message(
            "❌ Este comando solo funciona dentro de un servidor.",
            ephemeral=True
        )
        return

    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "❌ No pude verificar tu canal de voz.",
            ephemeral=True
        )
        return

    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message(
            "🎧 Primero entra a un canal de voz.",
            ephemeral=True
        )
        return

    await interaction.response.defer()

    player = get_player(interaction.guild.id)
    channel = interaction.user.voice.channel

    try:
        if player.voice and player.voice.is_connected():
            if player.voice.channel != channel:
                await player.voice.move_to(channel)
        else:
            player.voice = await channel.connect()

        track = await extract_track(query)

    except Exception as error:
        print(f"Error buscando canción: {error}")
        await interaction.followup.send(
            "❌ No pude encontrar/reproducir esa canción.\n"
            "Comprueba el nombre o el enlace."
        )
        return

    player.queue.append(track)

    was_playing = player.voice.is_playing() or player.voice.is_paused()

    if not was_playing and player.current is None:
        await player.play_next()

        embed = discord.Embed(
            title="🎵 Reproduciendo ahora",
            description=f"**[{track.title}]({track.webpage_url})**",
        )
        embed.add_field(
            name="Duración",
            value=format_duration(track.duration)
        )
        embed.set_footer(text=f"Solicitado por {interaction.user.display_name}")

        await interaction.followup.send(
            embed=embed,
            view=MusicControls(player)
        )
    else:
        position = len(player.queue)

        await interaction.followup.send(
            f"🎶 **Añadida a la cola:** [{track.title}]({track.webpage_url})\n"
            f"📋 Posición: **{position}**"
        )


# ============================================================
# /PAUSE
# ============================================================

@bot.tree.command(name="pause", description="Pausa la canción.")
async def pause(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)
    voice = player.voice

    if voice and voice.is_playing():
        voice.pause()
        await interaction.response.send_message("⏸️ Música pausada.")
    else:
        await interaction.response.send_message(
            "❌ No hay una canción reproduciéndose.",
            ephemeral=True
        )


# ============================================================
# /RESUME
# ============================================================

@bot.tree.command(name="resume", description="Reanuda la canción.")
async def resume(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)
    voice = player.voice

    if voice and voice.is_paused():
        voice.resume()
        await interaction.response.send_message("▶️ Música reanudada.")
    else:
        await interaction.response.send_message(
            "❌ La música no está pausada.",
            ephemeral=True
        )


# ============================================================
# /SKIP
# ============================================================

@bot.tree.command(name="skip", description="Salta la canción actual.")
async def skip(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)

    if player.voice and player.voice.is_playing():
        player.voice.stop()
        await interaction.response.send_message("⏭️ Canción saltada.")
    else:
        await interaction.response.send_message(
            "❌ No hay una canción reproduciéndose.",
            ephemeral=True
        )


# ============================================================
# /STOP
# ============================================================

@bot.tree.command(name="stop", description="Detiene la música y limpia la cola.")
async def stop(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)

    player.queue.clear()

    if player.voice and player.voice.is_playing():
        player.voice.stop()

    player.current = None

    await interaction.response.send_message(
        "⏹️ Música detenida y cola limpiada."
    )


# ============================================================
# /QUEUE
# ============================================================

@bot.tree.command(name="queue", description="Muestra la cola de canciones.")
async def queue(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)

    if not player.current and not player.queue:
        await interaction.response.send_message(
            "📋 La cola está vacía.",
            ephemeral=True
        )
        return

    embed = discord.Embed(title="🎶 Cola de música")

    if player.current:
        embed.add_field(
            name="▶️ Reproduciendo",
            value=f"[{player.current.title}]({player.current.webpage_url})",
            inline=False
        )

    if player.queue:
        lines = []
        for index, track in enumerate(player.queue[:10], start=1):
            lines.append(
                f"`{index}.` [{track.title}]({track.webpage_url})"
            )

        embed.add_field(
            name=f"📋 Próximas ({len(player.queue)})",
            value="\n".join(lines),
            inline=False
        )

        if len(player.queue) > 10:
            embed.set_footer(
                text=f"Y {len(player.queue) - 10} canción(es) más..."
            )

    await interaction.response.send_message(embed=embed)


# ============================================================
# /NOWPLAYING
# ============================================================

@bot.tree.command(
    name="nowplaying",
    description="Muestra la canción actual."
)
async def nowplaying(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)

    if not player.current:
        await interaction.response.send_message(
            "❌ No hay ninguna canción reproduciéndose.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="🎵 Reproduciendo ahora",
        description=f"[{player.current.title}]({player.current.webpage_url})"
    )
    embed.add_field(
        name="Duración",
        value=format_duration(player.current.duration)
    )

    await interaction.response.send_message(embed=embed)


# ============================================================
# /VOLUME
# ============================================================

@bot.tree.command(
    name="volume",
    description="Cambia el volumen del bot (0-100)."
)
@app_commands.describe(level="Volumen entre 0 y 100")
async def volume(interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]):
    player = get_player(interaction.guild.id)
    player.volume = level / 100

    if player.voice and player.voice.source:
        source = player.voice.source

        if isinstance(source, discord.PCMVolumeTransformer):
            source.volume = player.volume

    await interaction.response.send_message(
        f"🔊 Volumen establecido en **{level}%**."
    )


# ============================================================
# /LEAVE
# ============================================================

@bot.tree.command(
    name="leave",
    description="Desconecta el bot del canal de voz."
)
async def leave(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)

    player.queue.clear()
    player.current = None

    if player.voice and player.voice.is_connected():
        await player.voice.disconnect()
        player.voice = None

        await interaction.response.send_message(
            "👋 Me desconecté del canal de voz."
        )
    else:
        await interaction.response.send_message(
            "❌ No estoy conectado a un canal de voz.",
            ephemeral=True
        )


# ============================================================
# /HELP
# ============================================================

@bot.tree.command(
    name="musichelp",
    description="Muestra los comandos de música."
)
async def musichelp(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎵 Comandos de música",
        description="Puedes usar nombres de canciones o enlaces.",
    )

    embed.add_field(
        name="▶️ Reproducción",
        value=(
            "`/play nombre` — Buscar y reproducir\n"
            "`/play enlace` — Reproducir desde un enlace"
        ),
        inline=False
    )

    embed.add_field(
        name="🎛️ Controles",
        value=(
            "`/pause` — Pausar\n"
            "`/resume` — Reanudar\n"
            "`/skip` — Siguiente\n"
            "`/stop` — Detener\n"
            "`/volume 50` — Volumen\n"
            "`/leave` — Salir del canal"
        ),
        inline=False
    )

    embed.add_field(
        name="📋 Información",
        value=(
            "`/queue` — Ver cola\n"
            "`/nowplaying` — Canción actual"
        ),
        inline=False
    )

    await interaction.response.send_message(embed=embed)


# ============================================================
# INICIAR
# ============================================================

bot.run(TOKEN)

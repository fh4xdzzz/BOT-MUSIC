import os
import asyncio
import random
from datetime import datetime, timezone

import discord
import yt_dlp
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button

# ============================================================
# CONFIGURACIÓN
# ============================================================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("No se encontró DISCORD_TOKEN en las variables de entorno.")

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# Presets de equalizador
EQUALIZER_PRESETS = {
    "flat": "",  # Sin ecualización
    "rock": "equalizer=f=100:0.1:1:0.5:0.2:2",
    "pop": "equalizer=f=100:0.2:0.2:0.3:0.2:2",
    "classical": "equalizer=f=100:0.1:0.1:0.1:0.1:2",
    "bass": "bass=g=10",
    "treble": "treble=g=5",
    "vocal": "equalizer=f=100:0.2:0.3:0.2:0.1:2",
    "boost": "equalizer=f=100:0.2:0.2:0.2:0.2:2,bass=g=8,treble=g=5"
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

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
music_players = {}


# ============================================================
# MODELOS
# ============================================================
class Track:
    def __init__(self, title, stream_url, webpage_url, duration=0, thumbnail=None, uploader=None):
        self.title = title
        self.stream_url = stream_url
        self.webpage_url = webpage_url
        self.duration = duration or 0
        self.thumbnail = thumbnail
        self.uploader = uploader or "YouTube"


class GuildMusic:
    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.queue = []
        self.current = None
        self.voice = None
        self.volume = 0.5
        self.loop = False
        self.panel_message = None
        self.started_at = None
        self.equalizer = "flat"  # Equalizer activo
        self.lock = asyncio.Lock()

    def elapsed(self):
        if not self.started_at or not self.current:
            return 0
        if self.voice and self.voice.is_paused():
            return min(self.current.duration, int((self.paused_at - self.started_at).total_seconds())) if hasattr(self, "paused_at") else 0
        return max(0, int((datetime.now(timezone.utc) - self.started_at).total_seconds()))

    async def play_next(self):
        async with self.lock:
            if not self.voice or not self.voice.is_connected():
                self.current = None
                return

            if self.loop and self.current:
                track = self.current
            elif self.queue:
                track = self.queue.pop(0)
            else:
                self.current = None
                await update_panel(self)
                return

            self.current = track
            self.started_at = datetime.now(timezone.utc)
            self.paused_at = None

            # Aplicar equalizador si no es "flat"
            eq_filter = EQUALIZER_PRESETS.get(self.equalizer, "")
            ffmpeg_opts = FFMPEG_OPTIONS.copy()
            if eq_filter:
                ffmpeg_opts["options"] += f" {eq_filter}"

            source = discord.FFmpegPCMAudio(track.stream_url, **ffmpeg_opts)
            source = discord.PCMVolumeTransformer(source, volume=self.volume)

            def after(error):
                if error:
                    print(f"[Guild {self.guild_id}] Error de reproducción: {error}")
                asyncio.run_coroutine_threadsafe(self.play_next(), bot.loop)

            self.voice.play(source, after=after)
            print(f"[Guild {self.guild_id}] ▶ {track.title}")

        await update_panel(self)


def get_player(guild_id):
    if guild_id not in music_players:
        music_players[guild_id] = GuildMusic(guild_id)
    return music_players[guild_id]


# ============================================================
# YT-DLP
# ============================================================
async def extract_track(query: str):
    loop = asyncio.get_running_loop()

    def extract():
        with yt_dlp.YoutubeDL(YTDLP_OPTIONS) as ydl:
            info = ydl.extract_info(query, download=False)
            if "entries" in info:
                entries = [x for x in info["entries"] if x]
                if not entries:
                    raise ValueError("No encontré resultados.")
                info = entries[0]

            return Track(
                title=info.get("title", "Canción desconocida"),
                stream_url=info["url"],
                webpage_url=info.get("webpage_url", query),
                duration=info.get("duration", 0),
                thumbnail=info.get("thumbnail"),
                uploader=info.get("uploader") or "YouTube",
            )

    return await loop.run_in_executor(None, extract)


def format_duration(seconds):
    if not seconds:
        return "LIVE"
    seconds = int(seconds)
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def progress_bar(elapsed, total, size=18):
    if not total:
        return "🔴 LIVE"
    ratio = max(0, min(1, elapsed / total))
    pos = min(size - 1, int(ratio * size))
    chars = ["▬"] * size
    chars[pos] = "🔘"
    return "".join(chars)


def make_now_playing_embed(player: GuildMusic):
    embed = discord.Embed(
        title="🎵 Now Playing...",
        description="",
    )

    track = player.current
    if not track:
        embed.description = "No hay ninguna canción reproduciéndose.\nUsa **/play** para comenzar."
        return embed

    elapsed = min(player.elapsed(), track.duration) if track.duration else 0
    status = "⏸️ PAUSED" if player.voice and player.voice.is_paused() else "▶️ LIVE"

    embed.set_author(name=f"Playing from {track.uploader}")
    embed.description = (
        f"**[{track.title}]({track.webpage_url})**\n"
        f"{progress_bar(elapsed, track.duration)}\n"
        f"`{format_duration(elapsed)}` / `{format_duration(track.duration)}` • {status}"
    )

    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)

    embed.set_footer(text="Groove Music")
    return embed


async def update_panel(player: GuildMusic):
    if not player.panel_message:
        return
    try:
        await player.panel_message.edit(
            content=None,
            embed=make_now_playing_embed(player),
            view=MusicControls(player),
        )
    except (discord.NotFound, discord.HTTPException):
        player.panel_message = None


# ============================================================
# BOTONES
# ============================================================
class MusicControls(View):
    def __init__(self, player):
        super().__init__(timeout=None)
        self.player = player

    async def deny_if_not_in_voice(self, interaction):
        if not isinstance(interaction.user, discord.Member):
            return False
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("🎧 Entra primero a un canal de voz.", ephemeral=True)
            return False
        return True

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary, custom_id="music:pause")
    async def pause(self, interaction: discord.Interaction, button: Button):
        voice = self.player.voice
        if voice and voice.is_playing():
            self.player.paused_at = datetime.now(timezone.utc)
            voice.pause()
            await interaction.response.send_message("⏸️ Música pausada.", ephemeral=True)
        elif voice and voice.is_paused():
            voice.resume()
            await interaction.response.send_message("▶️ Música reanudada.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ No hay música reproduciéndose.", ephemeral=True)
        await update_panel(self.player)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="music:skip")
    async def skip(self, interaction: discord.Interaction, button: Button):
        if not self.player.voice or not self.player.voice.is_playing():
            await interaction.response.send_message("❌ No hay música reproduciéndose.", ephemeral=True)
            return
        self.player.voice.stop()
        await interaction.response.send_message("⏭️ Canción saltada.", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="music:stop")
    async def stop(self, interaction: discord.Interaction, button: Button):
        self.player.queue.clear()
        self.player.loop = False
        self.player.current = None
        if self.player.voice and self.player.voice.is_playing():
            self.player.voice.stop()
        await interaction.response.send_message("⏹️ Reproducción detenida y cola limpiada.", ephemeral=True)
        await update_panel(self.player)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="music:loop")
    async def loop(self, interaction: discord.Interaction, button: Button):
        self.player.loop = not self.player.loop
        await interaction.response.send_message(
            f"🔁 Repetición **{'activada' if self.player.loop else 'desactivada'}**.",
            ephemeral=True,
        )
        await update_panel(self.player)

    @discord.ui.button(emoji="🔄", style=discord.ButtonStyle.secondary, custom_id="music:replay")
    async def replay(self, interaction: discord.Interaction, button: Button):
        if not self.player.current or not self.player.voice or not self.player.voice.is_connected():
            await interaction.response.send_message("❌ No hay canción para repetir.", ephemeral=True)
            return
        current = self.player.current
        self.player.queue.insert(0, current)
        self.player.loop = False
        self.player.voice.stop()
        await interaction.response.send_message("🔄 Reiniciando canción.", ephemeral=True)

    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.secondary, custom_id="music:queue")
    async def show_queue(self, interaction: discord.Interaction, button: Button):
        if not self.player.queue:
            text = "La cola está vacía."
        else:
            text = "\n".join(
                f"`{i}.` {track.title}" for i, track in enumerate(self.player.queue[:10], 1)
            )
            if len(self.player.queue) > 10:
                text += f"\n... y {len(self.player.queue) - 10} más."
        await interaction.response.send_message(f"📜 **Cola**\n{text}", ephemeral=True)

    @discord.ui.button(emoji="➕", style=discord.ButtonStyle.secondary, custom_id="music:add")
    async def add_hint(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("➕ Usa **/play nombre o enlace** para añadir una canción.", ephemeral=True)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="music:shuffle")
    async def shuffle(self, interaction: discord.Interaction, button: Button):
        random.shuffle(self.player.queue)
        await interaction.response.send_message("🔀 Cola mezclada.", ephemeral=True)

    @discord.ui.button(emoji="🎚️", style=discord.ButtonStyle.secondary, custom_id="music:volume")
    async def volume(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            f"🎚️ Volumen actual: **{round(self.player.volume * 100)}%**\nUsa `/volume 0-100` para cambiarlo.",
            ephemeral=True,
        )

    @discord.ui.button(emoji="❤️", style=discord.ButtonStyle.secondary, custom_id="music:favorite")
    async def favorite(self, interaction: discord.Interaction, button: Button):
        if self.player.current:
            await interaction.response.send_message(
                f"❤️ **{self.player.current.title}** marcada como favorita para esta sesión.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message("❌ No hay canción actual.", ephemeral=True)

    @discord.ui.button(emoji="🎚️", style=discord.ButtonStyle.secondary, custom_id="music:equalizer")
    async def equalizer(self, interaction: discord.Interaction, button: Button):
        presets = ["flat", "rock", "pop", "classical", "bass", "treble", "vocal", "boost"]
        current = self.player.equalizer
        
        embed = discord.Embed(
            title="🎚️ Equalizer",
            description=f"Actual: **{current.upper()}**\n\nSelecciona un preset:",
            color=discord.Color.purple()
        )
        
        for i, preset in enumerate(presets):
            status = "✅" if preset == current else "⬜"
            embed.add_field(name=f"{status} {preset}", value=EQUALIZER_PRESETS[preset] or "Sin filtros", inline=True)
        
        embed.set_footer(text="Usa /equalizer [preset] para cambiar directamente")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ============================================================
# COMANDO PLAY
# ============================================================
@bot.tree.command(name="play", description="Reproduce una canción por nombre o enlace.")
@app_commands.describe(query="Nombre de la canción o enlace")
async def play(interaction: discord.Interaction, query: str):
    if not interaction.guild:
        await interaction.response.send_message("❌ Usa este comando en un servidor.", ephemeral=True)
        return
    if not isinstance(interaction.user, discord.Member) or not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("🎧 Primero entra a un canal de voz.", ephemeral=True)
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
        await interaction.followup.send("❌ No pude encontrar/reproducir esa canción. Comprueba el nombre o enlace.")
        return

    was_playing = player.voice.is_playing() or player.voice.is_paused()
    player.queue.append(track)

    if not was_playing and player.current is None:
        await player.play_next()
        msg = await interaction.followup.send(
            embed=make_now_playing_embed(player),
            view=MusicControls(player),
            wait=True,
        )
        player.panel_message = msg
    else:
        await interaction.followup.send(
            f"🎶 Añadida a la cola: **{track.title}** • posición **{len(player.queue)}**"
        )


# ============================================================
# COMANDOS RESTANTES
# ============================================================
@bot.tree.command(name="pause", description="Pausa la música.")
async def pause(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)
    if player.voice and player.voice.is_playing():
        player.voice.pause()
        await interaction.response.send_message("⏸️ Pausado.")
        await update_panel(player)
    else:
        await interaction.response.send_message("❌ No hay música reproduciéndose.", ephemeral=True)


@bot.tree.command(name="resume", description="Reanuda la música.")
async def resume(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)
    if player.voice and player.voice.is_paused():
        player.voice.resume()
        await interaction.response.send_message("▶️ Reanudado.")
        await update_panel(player)
    else:
        await interaction.response.send_message("❌ La música no está pausada.", ephemeral=True)


@bot.tree.command(name="skip", description="Salta la canción actual.")
async def skip(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)
    if player.voice and player.voice.is_playing():
        player.voice.stop()
        await interaction.response.send_message("⏭️ Canción saltada.")
    else:
        await interaction.response.send_message("❌ No hay música reproduciéndose.", ephemeral=True)


@bot.tree.command(name="stop", description="Detiene la música y limpia la cola.")
async def stop(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)
    player.queue.clear()
    player.loop = False
    if player.voice and (player.voice.is_playing() or player.voice.is_paused()):
        player.voice.stop()
    player.current = None
    await interaction.response.send_message("⏹️ Música detenida y cola limpiada.")
    await update_panel(player)


@bot.tree.command(name="queue", description="Muestra la cola.")
async def queue(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)
    if not player.queue:
        await interaction.response.send_message("📜 La cola está vacía.", ephemeral=True)
        return
    lines = [f"`{i}.` {track.title}" for i, track in enumerate(player.queue[:20], 1)]
    await interaction.response.send_message("📜 **Cola**\n" + "\n".join(lines))


@bot.tree.command(name="nowplaying", description="Muestra la canción actual.")
async def nowplaying(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)
    await interaction.response.send_message(embed=make_now_playing_embed(player), view=MusicControls(player))


@bot.tree.command(name="volume", description="Cambia el volumen (0-100).")
@app_commands.describe(level="Volumen entre 0 y 100")
async def volume(interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]):
    player = get_player(interaction.guild.id)
    player.volume = level / 100
    if player.voice and player.voice.source and isinstance(player.voice.source, discord.PCMVolumeTransformer):
        player.voice.source.volume = player.volume
    await interaction.response.send_message(f"🔊 Volumen: **{level}%**")


@bot.tree.command(name="leave", description="Desconecta el bot del canal de voz.")
async def leave(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)
    player.queue.clear()
    player.current = None
    if player.voice and player.voice.is_connected():
        await player.voice.disconnect()
        player.voice = None
        await interaction.response.send_message("👋 Me desconecté del canal de voz.")
    else:
        await interaction.response.send_message("❌ No estoy en un canal de voz.", ephemeral=True)


@bot.tree.command(name="equalizer", description="Cambia el preset de equalizador.")
@app_commands.describe(preset="Preset de equalizador (flat, rock, pop, classical, bass, treble, vocal, boost)")
async def equalizer(interaction: discord.Interaction, preset: str):
    player = get_player(interaction.guild.id)
    
    if preset not in EQUALIZER_PRESETS:
        presets = ", ".join(EQUALIZER_PRESETS.keys())
        await interaction.response.send_message(f"❌ Preset inválido. Disponibles: {presets}", ephemeral=True)
        return
    
    player.equalizer = preset
    
    # Si hay música reproduciéndose, cambiar equalizador requiere reiniciar la canción
    if player.voice and player.voice.is_playing():
        player.current = None
        player.voice.stop()
        if player.queue:
            await player.play_next()
        await interaction.response.send_message(f"🎚️ Equalizador cambiado a **{preset.upper()}** - reproducción reiniciada")
    else:
        await interaction.response.send_message(f"🎚️ Equalizador cambiado a **{preset.upper()}**")


# ============================================================
# EVENTOS / ACTUALIZACIÓN
# ============================================================
@bot.event
async def on_ready():
    print("==========================================")
    print(f"✅ Bot conectado: {bot.user}")
    print(f"🌐 Servidores: {len(bot.guilds)}")
    print("==========================================")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Slash commands sincronizados: {len(synced)}")
    except Exception as error:
        print(f"❌ Error sincronizando comandos: {error}")
    if not panel_updater.is_running():
        panel_updater.start()


@bot.event
async def on_voice_state_update(member, before, after):
    if bot.user and member.id == bot.user.id and before.channel and not after.channel:
        player = music_players.get(member.guild.id)
        if player:
            player.voice = None
            player.current = None
            player.panel_message = None


@tasks.loop(seconds=15)
async def panel_updater():
    for player in list(music_players.values()):
        if player.current and player.panel_message:
            await update_panel(player)


@panel_updater.before_loop
async def before_panel_updater():
    await bot.wait_until_ready()


bot.run(TOKEN)

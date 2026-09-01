import os
import asyncio
import random
from datetime import datetime, timezone

import discord
import yt_dlp
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput, Select

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
EQ_BANDS = [
    (31, "31 Hz"),
    (62, "62 Hz"),
    (125, "125 Hz"),
    (250, "250 Hz"),
    (500, "500 Hz"),
    (1000, "1 kHz"),
    (2000, "2 kHz"),
    (4000, "4 kHz"),
    (8000, "8 kHz"),
    (16000, "16 kHz"),
]

EQ_PRESETS = {
    "flat": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "bass": [6, 5, 4, 2, 0, 0, -1, -1, -1, -1],
    "rock": [4, 3, 1, -1, -2, 1, 3, 4, 4, 3],
    "pop": [-1, 1, 3, 4, 2, -1, -1, 1, 3, 2],
    "vocal": [-3, -2, -1, 2, 4, 5, 4, 2, 0, -1],
    "electronic": [5, 4, 2, 0, -1, 1, 3, 4, 5, 4],
    "night": [-2, -1, 0, 1, 2, 3, 2, 1, 0, -1],
}

EQ_NAMES = {
    "flat": "Flat",
    "bass": "Bass Boost",
    "rock": "Rock",
    "pop": "Pop",
    "vocal": "Vocal",
    "electronic": "Electronic",
    "night": "Night Mode",
}

def clamp_gain(value):
    return max(-12.0, min(12.0, float(value)))

def eq_filter(gains):
    parts = []
    for (freq, _), gain in zip(EQ_BANDS, gains):
        gain = clamp_gain(gain)
        if abs(gain) >= 0.01:
            parts.append(f"equalizer=f={freq}:t=q:w=1:g={gain:.2f}")
    return ",".join(parts) if parts else "anull"

def eq_summary(gains):
    chunks = []
    for (_, label), gain in zip(EQ_BANDS, gains):
        if abs(gain) >= 0.01:
            chunks.append(f"{label}: {'+' if gain > 0 else ''}{gain:.1f} dB")
    return " • ".join(chunks) if chunks else "Flat (sin realce)"

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
        self.eq_enabled = True
        self.eq_gains = EQ_PRESETS["flat"].copy()
        self.eq_preset = "flat"
        self.loop = False
        self.panel_message = None
        self.started_at = None
        self.lock = asyncio.Lock()
        self.suppress_after = False

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

            source = discord.FFmpegPCMAudio(
                track.stream_url,
                before_options=FFMPEG_OPTIONS["before_options"],
                options=f"-vn -af {eq_filter(self.eq_gains) if self.eq_enabled else 'anull'}",
            )
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

    preset = EQ_NAMES.get(player.eq_preset, "Custom")
    eq_state = "ON" if player.eq_enabled else "OFF"
    embed.set_footer(text=f"Groove Music • EQ {eq_state} • {preset}")
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
class EqualizerModal(Modal):
    def __init__(self, player, start_index=0):
        title = "🎚️ EQ — Bandas 1-5" if start_index == 0 else "🎚️ EQ — Bandas 6-10"
        super().__init__(title=title, timeout=180)
        self.player = player
        self.start_index = start_index
        self.inputs = []

        for i in range(start_index, min(start_index + 5, len(EQ_BANDS))):
            freq, label = EQ_BANDS[i]
            current = player.eq_gains[i]
            field = TextInput(
                label=label,
                placeholder="-12 a +12 dB",
                default=f"{current:.1f}",
                required=True,
                min_length=1,
                max_length=6,
            )
            self.inputs.append((i, field))
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            for i, field in self.inputs:
                self.player.eq_gains[i] = clamp_gain(float(field.value.replace(",", ".")))
        except ValueError:
            await interaction.response.send_message(
                "❌ Usa solo números entre **-12 y +12 dB**.", ephemeral=True
            )
            return

        self.player.eq_enabled = True
        self.player.eq_preset = "custom"

        if self.start_index == 0:
            await interaction.response.send_message(
                "🎚️ **Bandas 1-5 guardadas.** Ahora puedes editar las bandas 6-10 desde el panel del ecualizador.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "🎚️ **Ecualizador personalizado guardado.**\n" + eq_summary(self.player.eq_gains),
                ephemeral=True,
            )

        await restart_current_with_eq(self.player)


class EqualizerSelect(Select):
    def __init__(self, player):
        options = [
            discord.SelectOption(label=name, value=key, description="Aplicar este perfil al audio")
            for key, name in EQ_NAMES.items()
        ]
        options.append(discord.SelectOption(label="Personalizado", value="custom", description="Configura las 10 bandas manualmente"))
        options.append(discord.SelectOption(label="Bypass / Sin EQ", value="bypass", description="Desactiva el procesamiento del ecualizador"))
        super().__init__(placeholder="Selecciona un perfil de audio...", options=options, custom_id="music:eq:select")
        self.player = player

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        if value == "custom":
            await interaction.response.send_modal(EqualizerModal(self.player))
            return
        if value == "bypass":
            self.player.eq_enabled = False
            self.player.eq_preset = "flat"
            await interaction.response.send_message("🎚️ **Ecualizador desactivado.**", ephemeral=True)
        else:
            self.player.eq_enabled = True
            self.player.eq_preset = value
            self.player.eq_gains = EQ_PRESETS[value].copy()
            await interaction.response.send_message(
                f"🎚️ Perfil **{EQ_NAMES[value]}** aplicado.\n{eq_summary(self.player.eq_gains)}",
                ephemeral=True,
            )
        await restart_current_with_eq(self.player)


class EqualizerView(View):
    def __init__(self, player):
        super().__init__(timeout=180)
        self.add_item(EqualizerSelect(player))
        self.player = player

    @discord.ui.button(label="🎚️ Bandas 1-5", style=discord.ButtonStyle.primary, custom_id="music:eq:low")
    async def low_bands(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(EqualizerModal(self.player, 0))

    @discord.ui.button(label="🎚️ Bandas 6-10", style=discord.ButtonStyle.primary, custom_id="music:eq:high")
    async def high_bands(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(EqualizerModal(self.player, 5))

    @discord.ui.button(label="⏺️ Activar / Desactivar", style=discord.ButtonStyle.secondary, custom_id="music:eq:toggle")
    async def toggle(self, interaction: discord.Interaction, button: Button):
        self.player.eq_enabled = not self.player.eq_enabled
        state = "activado" if self.player.eq_enabled else "desactivado"
        await interaction.response.send_message(f"🎚️ Ecualizador **{state}**.", ephemeral=True)
        await restart_current_with_eq(self.player)


async def restart_current_with_eq(player: GuildMusic):
    """Reinicia el stream actual para aplicar el filtro FFmpeg nuevo."""
    if not player.current or not player.voice or not player.voice.is_connected():
        await update_panel(player)
        return

    current = player.current
    # Evitamos que el callback del stop salte a la siguiente pista.
    player.suppress_after = True
    if player.voice.is_playing() or player.voice.is_paused():
        player.voice.stop()
        await asyncio.sleep(0.15)

    player.started_at = datetime.now(timezone.utc)
    player.paused_at = None
    source = discord.FFmpegPCMAudio(
        current.stream_url,
        before_options=FFMPEG_OPTIONS["before_options"],
        options=f"-vn -af {eq_filter(player.eq_gains) if player.eq_enabled else 'anull'}",
    )
    source = discord.PCMVolumeTransformer(source, volume=player.volume)

    def after(error):
        if error:
            print(f"[Guild {player.guild_id}] Error de reproducción: {error}")
        if getattr(player, "suppress_after", False):
            player.suppress_after = False
            return
        asyncio.run_coroutine_threadsafe(player.play_next(), bot.loop)

    player.voice.play(source, after=after)
    await update_panel(player)


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

    @discord.ui.button(emoji="🎛️", style=discord.ButtonStyle.secondary, custom_id="music:eq")
    async def equalizer(self, interaction: discord.Interaction, button: Button):
        preset = EQ_NAMES.get(self.player.eq_preset, "Personalizado")
        state = "ON" if self.player.eq_enabled else "OFF"
        embed = discord.Embed(
            title="🎚️ Ecualizador Profesional",
            description=f"**Estado:** `{state}` • **Perfil:** `{preset}`\n\n{eq_summary(self.player.eq_gains)}\n\nSelecciona un preset o ajusta las 10 bandas en dos grupos. Los cambios se aplican al reproductor.",
        )
        await interaction.response.send_message(embed=embed, view=EqualizerView(self.player), ephemeral=True)

    @discord.ui.button(emoji="❤️", style=discord.ButtonStyle.secondary, custom_id="music:favorite")
    async def favorite(self, interaction: discord.Interaction, button: Button):
        if self.player.current:
            await interaction.response.send_message(
                f"❤️ **{self.player.current.title}** marcada como favorita para esta sesión.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message("❌ No hay canción actual.", ephemeral=True)


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


@bot.tree.command(name="equalizer", description="Abre el ecualizador profesional de 10 bandas.")
async def equalizer(interaction: discord.Interaction):
    player = get_player(interaction.guild.id)
    preset = EQ_NAMES.get(player.eq_preset, "Personalizado")
    embed = discord.Embed(
        title="🎚️ Ecualizador Profesional",
        description=(
            f"**Estado:** `{'ON' if player.eq_enabled else 'OFF'}` • **Perfil:** `{preset}`\n\n"
            f"{eq_summary(player.eq_gains)}\n\n"
            "Usa el menú para cambiar de preset o ajusta las **10 bandas** en dos grupos de 5, de **-12 a +12 dB** por banda."
        ),
    )
    await interaction.response.send_message(embed=embed, view=EqualizerView(player), ephemeral=True)


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

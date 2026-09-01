import os
import discord
from discord.ext import commands

# ==============================
# CONFIGURACIÓN
# ==============================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("❌ No se encontró la variable DISCORD_TOKEN en SparkedHost.")

PREFIX = "!"

# ==============================
# INTENTS
# ==============================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

# ==============================
# BOT
# ==============================

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None
)


# ==============================
# EVENTO: BOT LISTO
# ==============================

@bot.event
async def on_ready():
    print("===================================")
    print(f"✅ Bot conectado como: {bot.user}")
    print(f"🆔 ID: {bot.user.id}")
    print(f"🌐 Servidores: {len(bot.guilds)}")
    print("===================================")

    try:
        synced = await bot.tree.sync()
        print(f"✅ Slash commands sincronizados: {len(synced)}")
    except Exception as e:
        print(f"❌ Error sincronizando slash commands: {e}")


# ==============================
# COMANDO DE PRUEBA
# ==============================

@bot.command()
async def ping(ctx):
    """Comprueba si el bot está funcionando."""

    latency = round(bot.latency * 1000)

    await ctx.send(f"🏓 Pong! `{latency}ms`")


# ==============================
# SLASH COMMAND
# ==============================

@bot.tree.command(name="ping", description="Comprueba si el bot está funcionando")
async def slash_ping(interaction: discord.Interaction):

    latency = round(bot.latency * 1000)

    await interaction.response.send_message(
        f"🏓 Pong! `{latency}ms`"
    )


# ==============================
# ERROR HANDLER
# ==============================

@bot.event
async def on_command_error(ctx, error):

    if isinstance(error, commands.CommandNotFound):
        return

    print(f"❌ Error: {error}")


# ==============================
# INICIAR BOT
# ==============================

bot.run(TOKEN)

import discord
from discord.ext import commands
import re
import os
from flask import Flask
from threading import Thread

# --- Flaskでダミーサーバーを立てる (RenderのPort監視対策) ---
app = Flask('')
@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- Discord Botの設定 ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 環境変数から取得（RenderのDashboardで設定してください）
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
MONITOR_CHANNEL_ID = int(os.getenv("MONITOR_CHANNEL_ID", "0"))

# メモリ上に保持（再起動でリセットされますが、起動時にチャンネルから再取得します）
AUTO_DELETE_ENABLED = True
BLACKLIST_GUILD_IDS = set()

INVITE_REGEX = r"(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/([\w\-]+)"

async def update_blacklist():
    """特定のチャンネルからIDを読み込む"""
    channel = bot.get_channel(MONITOR_CHANNEL_ID)
    if channel:
        BLACKLIST_GUILD_IDS.clear()
        async for message in channel.history(limit=100):
            if message.content.isdigit():
                BLACKLIST_GUILD_IDS.add(int(message.content))
        print(f"Updated Blacklist: {BLACKLIST_GUILD_IDS}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await update_blacklist()

@bot.event
async def on_message(message):
    global AUTO_DELETE_ENABLED
    if message.author.bot:
        return

    # IDリストが更新されたら反映（特定のチャンネルに新しくIDが書かれた場合）
    if message.channel.id == MONITOR_CHANNEL_ID and message.content.isdigit():
        BLACKLIST_GUILD_IDS.add(int(message.content))
        return

    # フィルタリング処理
    if AUTO_DELETE_ENABLED:
        match = re.search(INVITE_REGEX, message.content)
        if match:
            invite_code = match.group(3)
            try:
                invite = await bot.fetch_invite(invite_code)
                if invite.guild and invite.guild.id in BLACKLIST_GUILD_IDS:
                    await message.delete()
                    await message.channel.send(f"⚠️ {message.author.mention} 禁止サーバーへの招待は貼れません。", delete_after=5)
            except:
                pass

    await bot.process_commands(message)

@bot.command()
@commands.has_permissions(administrator=True)
async def toggle(ctx):
    global AUTO_DELETE_ENABLED
    AUTO_DELETE_ENABLED = not AUTO_DELETE_ENABLED
    await ctx.send(f"フィルタリングを {'有効' if AUTO_DELETE_ENABLED else '無効'} にしました。")

# 実行
keep_alive()
bot.run(TOKEN)

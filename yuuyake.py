import discord
from discord import app_commands
from discord.ext import commands
import re
import os
from flask import Flask
from threading import Thread

# --- 設定値 ---
ID_LIST_CHANNEL_ID = 1472220342889218250 # 禁止IDが投稿されているチャンネル
LOG_CHANNEL_ID = 1472220342889218250     # ログ（検知通知）を送るチャンネル

app = Flask('')
@app.route('/')
def home(): return "Bot is alive!"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
def keep_alive(): Thread(target=run).start()

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
    async def setup_hook(self): await self.tree.sync()

bot = MyBot()

# --- 状態管理 ---
CHECK_JOIN_ENABLED = True    # 2. 参加時チェックのON/OFF
DELETE_INVITE_ENABLED = True # 3. 招待削除のON/OFF
BLACKLIST_GUILD_IDS = {1176515964561526914}     # {サーバーID: サーバー名}
INVITE_REGEX = r"(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/([\w\-]+)"

async def update_blacklist():
    channel = bot.get_channel(ID_LIST_CHANNEL_ID)
    if channel:
        BLACKLIST_GUILD_IDS.clear()
        messages = [m async for m in channel.history(limit=200)]
        for i, m in enumerate(messages):
            if m.content.isdigit():
                guild_id = int(m.content)
                guild_name = messages[i+1].content if i+1 < len(messages) else "不明なサーバー"
                BLACKLIST_GUILD_IDS[guild_id] = guild_name

@bot.event
async def on_ready():
    print(f"✅ {bot.user} 起動")
    await update_blacklist()

@bot.event
async def on_member_join(member):
    """2. 参加時チェック機能"""
    if not CHECK_JOIN_ENABLED: return
    for banned_id, banned_name in BLACKLIST_GUILD_IDS.items():
        banned_guild = bot.get_guild(banned_id)
        if banned_guild and banned_guild.get_member(member.id):
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(f"⚠️ **禁止鯖所属者検知**\nユーザー: {member.mention}\n該当鯖: {banned_name}\nID: `{banned_id}`")
            break

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id == ID_LIST_CHANNEL_ID and message.content.isdigit():
        await update_blacklist()
        return

    """3. 招待リンク削除機能"""
    if DELETE_INVITE_ENABLED:
        match = re.search(INVITE_REGEX, message.content)
        if match:
            invite_code = match.group(3)
            try:
                invite = await bot.fetch_invite(invite_code)
                if invite.guild and invite.guild.id in BLACKLIST_GUILD_IDS:
                    await message.delete()
                    await message.channel.send(f"⚠️ {message.author.mention} 禁止サーバーへの招待は削除されました。", delete_after=5)
            except: pass

# --- スラッシュコマンド ---

@bot.tree.command(name="toggle_join", description="参加時チェックのON/OFF")
@app_commands.checks.has_permissions(administrator=True)
async def toggle_join(interaction: discord.Interaction):
    global CHECK_JOIN_ENABLED
    CHECK_JOIN_ENABLED = not CHECK_JOIN_ENABLED
    await interaction.response.send_message(f"参加時チェックを **{'有効' if CHECK_JOIN_ENABLED else '無効'}** にしました。")

@bot.tree.command(name="toggle_invite", description="招待リンク削除のON/OFF")
@app_commands.checks.has_permissions(administrator=True)
async def toggle_invite(interaction: discord.Interaction):
    global DELETE_INVITE_ENABLED
    DELETE_INVITE_ENABLED = not DELETE_INVITE_ENABLED
    await interaction.response.send_message(f"招待リンク削除を **{'有効' if DELETE_INVITE_ENABLED else '無効'}** にしました。")

@bot.tree.command(name="reset_name", description="Botの名前とアバターをリセットします（一回限り推奨）")
@app_commands.checks.has_permissions(administrator=True)
async def reset_name(interaction: discord.Interaction, new_name: str):
    """Botの名前をリセット/変更するコマンド"""
    try:
        await bot.user.edit(username=new_name)
        await interaction.response.send_message(f"Botの名前を `{new_name}` に変更しました。")
    except Exception as e:
        await interaction.response.send_message(f"エラーが発生しました: {e}")

keep_alive()
bot.run(os.getenv("DISCORD_BOT_TOKEN"))

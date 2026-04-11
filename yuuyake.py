import discord
from discord import app_commands
from discord.ext import commands
import re
import os
from keep_alive import keep_alive

# --- 設定 ---
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
MONITOR_CHANNEL_ID = int(os.getenv("MONITOR_CHANNEL_ID", "0"))

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # スラッシュコマンドを同期（反映）させる
        await self.tree.sync()
        print("Slash commands synced!")

bot = MyBot()

AUTO_DELETE_ENABLED = True
BLACKLIST_GUILD_IDS = set()
INVITE_REGEX = r"(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/([\w\-]+)"

# 起動時にチャンネルからIDを読み込む
async def update_blacklist():
    channel = bot.get_channel(MONITOR_CHANNEL_ID)
    if channel:
        BLACKLIST_GUILD_IDS.clear()
        async for message in channel.history(limit=100):
            if message.content.isdigit():
                BLACKLIST_GUILD_IDS.add(int(message.content))
        print(f"Blacklist updated: {BLACKLIST_GUILD_IDS}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await update_blacklist()

# メッセージ監視（招待リンクの削除とIDの自動登録）
@bot.event
async def on_message(message):
    global AUTO_DELETE_ENABLED
    if message.author.bot:
        return

    # ID登録チャンネルでの処理
    if message.channel.id == MONITOR_CHANNEL_ID and message.content.isdigit():
        BLACKLIST_GUILD_IDS.add(int(message.content))
        return

    # 招待リンクの判定と削除
    if AUTO_DELETE_ENABLED:
        match = re.search(INVITE_REGEX, message.content)
        if match:
            invite_code = match.group(3)
            try:
                invite = await bot.fetch_invite(invite_code)
                if invite.guild and invite.guild.id in BLACKLIST_GUILD_IDS:
                    await message.delete()
                    await message.channel.send(f"⚠️ {message.author.mention} 禁止サーバーへの招待は削除されました。", delete_after=5)
            except:
                pass

# --- スラッシュコマンド部分 ---

@bot.tree.command(name="toggle", description="招待リンクフィルターの有効/無効を切り替えます")
@app_commands.checks.has_permissions(administrator=True) # 管理者のみ
async def toggle(interaction: discord.Interaction):
    global AUTO_DELETE_ENABLED
    AUTO_DELETE_ENABLED = not AUTO_DELETE_ENABLED
    status = "有効" if AUTO_DELETE_ENABLED else "無効"
    await interaction.response.send_message(f"フィルタリングを **{status}** にしました。")

# 実行
keep_alive()
bot.run(TOKEN)

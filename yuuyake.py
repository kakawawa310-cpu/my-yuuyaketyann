import discord
from discord import app_commands
from discord.ext import commands
import re
import os
from keep_alive()
import keep_alive()

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("Slash commands synced!")

bot = MyBot()

AUTO_DELETE_ENABLED = True
BLACKLIST_GUILD_IDS = set()
INVITE_REGEX = r"(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/([\w\-]+)"

async def update_blacklist():
    channel = bot.get_channel(1472220342889218250)
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

@bot.event
async def on_message(message):
    global AUTO_DELETE_ENABLED
    if message.author.bot:
        return

    if message.channel.id == 1472220342889218250 and message.content.isdigit():
        BLACKLIST_GUILD_IDS.add(int(message.content))
        return

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

@bot.tree.command(name="toggle", description="招待リンクフィルターの有効/無効を切り替えます")
@app_commands.checks.has_permissions(administrator=True)
async def toggle(interaction: discord.Interaction):
    global AUTO_DELETE_ENABLED
    AUTO_DELETE_ENABLED = not AUTO_DELETE_ENABLED
    status = "有効" if AUTO_DELETE_ENABLED else "無効"
    await interaction.response.send_message(f"フィルタリングを **{status}** にしました。")

# --- 実行部分 ---
keep_alive() # ← これを戻す
bot.run(os.getenv("DISCORD_BOT_TOKEN")) # ← これを追加

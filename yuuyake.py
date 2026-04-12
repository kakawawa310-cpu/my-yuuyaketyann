import discord
from discord import app_commands
from discord.ext import commands
import re
import os
from flask import Flask
from threading import Thread  # ← これが重要です！

# --- 1. Webサーバー設定 (Renderの停止防止) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    # ポートを 10000 に固定する
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# --- 2. Botのクラス定義 ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # メッセージ読み取り許可
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Slash commands synced!")

bot = MyBot()

# --- 3. 動作設定 ---
AUTO_DELETE_ENABLED = True
BLACKLIST_GUILD_IDS = set()
INVITE_REGEX = r"(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/([\w\-]+)"
CHANNEL_ID = 1472220342889218250 # サーバーIDが書かれているチャンネル

async def update_blacklist():
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        BLACKLIST_GUILD_IDS.clear()
        async for message in channel.history(limit=100):
            if message.content.isdigit():
                BLACKLIST_GUILD_IDS.add(int(message.content))
        print(f"✅ Blacklist updated: {BLACKLIST_GUILD_IDS}")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await update_blacklist()

@bot.event
async def on_message(message):
    global AUTO_DELETE_ENABLED
    if message.author.bot:
        return

    # ID登録チャンネルでの処理
    if message.channel.id == CHANNEL_ID and message.content.isdigit():
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

# --- 4. スラッシュコマンド ---
@bot.tree.command(name="toggle", description="招待リンクフィルターのON/OFF")
@app_commands.checks.has_permissions(administrator=True)
async def toggle(interaction: discord.Interaction):
    global AUTO_DELETE_ENABLED
    AUTO_DELETE_ENABLED = not AUTO_DELETE_ENABLED
    status = "有効" if AUTO_DELETE_ENABLED else "無効"
    await interaction.response.send_message(f"フィルタリングを **{status}** にしました。")

if __name__ == "__main__":
    keep_alive()
    token = os.getenv("DISCORD_BOT_TOKEN")
    
    # ログに出力して確認
    if token:
        print(f"✅ トークンを発見（先頭5文字: {token[:5]}...）")
        bot.run(token)
    else:
        print("❌ エラー: Renderの設定画面で 'DISCORD_BOT_TOKEN' が見つかりません！")

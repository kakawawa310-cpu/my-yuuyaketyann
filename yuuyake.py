import discord
from discord import app_commands
from discord.ext import commands
import re
import os
from flask import Flask
from threading import Thread

# --- 設定値 ---
# 禁止サーバーIDが投稿されるチャンネルID
CHANNEL_ID = 1472220342889218250 

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # 入室検知に必要
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Slash commands synced!")

bot = MyBot()

# --- 状態管理 ---
SYSTEM_ENABLED = True
BLACKLIST_GUILD_IDS = {} # {サーバーID: サーバー名}
INVITE_REGEX = r"(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/([\w\-]+)"

async def update_blacklist():
    """チャンネル履歴から禁止サーバーリストを更新"""
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        BLACKLIST_GUILD_IDS.clear()
        # 履歴を200件取得して解析
        messages = [m async for m in channel.history(limit=200)]
        for i, m in enumerate(messages):
            if m.content.isdigit():
                guild_id = int(m.content)
                # 1行上（メッセージリストでは次の要素）を名前として取得
                guild_name = messages[i+1].content if i+1 < len(messages) else "不明なサーバー"
                BLACKLIST_GUILD_IDS[guild_id] = guild_name
        print(f"✅ 禁止リストを更新しました: {len(BLACKLIST_GUILD_IDS)}件")

@bot.event
async def on_ready():
    print(f"✅ {bot.user} としてログインしました")
    await update_blacklist()

@bot.event
async def on_member_join(member):
    """新しい人が参加した時、禁止鯖にいないかチェック"""
    if not SYSTEM_ENABLED:
        return
    
    # 禁止リストにあるサーバーを一つずつ確認
    for banned_id, banned_name in BLACKLIST_GUILD_IDS.items():
        # Botが共通で入っているサーバーのみ判定可能
        banned_guild = bot.get_guild(banned_id)
        if banned_guild and banned_guild.get_member(member.id):
            log_channel = bot.get_channel(CHANNEL_ID)
            if log_channel:
                await log_channel.send(
                    f"⚠️ **禁止サーバー所属者を検知**\n"
                    f"ユーザー: {member.mention} ({member.name})\n"
                    f"該当サーバー: **{banned_name}**\n"
                    f"サーバーID: `{banned_id}`"
                )
            break

@bot.event
async def on_message(message):
    global SYSTEM_ENABLED
    if message.author.bot:
        return

    # ID登録チャンネルで数字が打たれたらリスト更新
    if message.channel.id == CHANNEL_ID and message.content.isdigit():
        await update_blacklist()
        return

    # 招待リンクの判定と削除
    if SYSTEM_ENABLED:
        match = re.search(INVITE_REGEX, message.content)
        if match:
            invite_code = match.group(3)
            try:
                invite = await bot.fetch_invite(invite_code)
                if invite.guild and invite.guild.id in BLACKLIST_GUILD_IDS:
                    await message.delete()
                    await message.channel.send(
                        f"⚠️ {message.author.mention} 禁止サーバー「{BLACKLIST_GUILD_IDS[invite.guild.id]}」への招待は許可されていません。", 
                        delete_after=7
                    )
            except:
                pass

# --- スラッシュコマンド ---
@bot.tree.command(name="toggle", description="システムのON/OFFを切り替えます")
@app_commands.checks.has_permissions(administrator=True)
async def toggle(interaction: discord.Interaction):
    global SYSTEM_ENABLED
    SYSTEM_ENABLED = not SYSTEM_ENABLED
    status = "有効" if SYSTEM_ENABLED else "無効"
    await interaction.response.send_message(f"フィルタリングシステムを **{status}** にしました。")

# Webサーバー起動
keep_alive()

# Bot起動（環境変数の名前をDISCORD_BOT_TOKENに合わせる）
bot.run(os.getenv("DISCORD_BOT_TOKEN"))

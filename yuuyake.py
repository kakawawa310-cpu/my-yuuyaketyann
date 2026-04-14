import discord
from discord import app_commands
from discord.ext import commands
import re
import os
from flask import Flask
from threading import Thread  # ← これが重要です！

# --- Webサーバーの設定 ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    # RenderはデフォルトでPORT環境変数を使用するため、それに合わせる
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
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

# 設定値
BANNED_GUILD_ID = 1472220342889218250

class RoleSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        placeholder="付与したいロールを選んでください",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="ロールA", value="111222333444"), # valueにロールID
            discord.SelectOption(label="ロールB", value="555666777888"),
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        # 1. 禁止サーバーにユーザーがいるかチェック
        # ※Botがそのサーバーに入っている必要があります
        banned_guild = interaction.client.get_guild(BANNED_GUILD_ID)
        
        if banned_guild and banned_guild.get_member(interaction.user.id):
            return await interaction.response.send_message(
                "【認証エラー】特定のサーバーに所属しているため、ロールを付与できません。", 
                ephemeral=True
            )

        # 2. 選択されたロールを取得して付与
        role_id = int(select.values[0])
        role = interaction.guild.get_role(role_id)

        if role:
            try:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(f"「{role.name}」を付与しました！", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("Botにロール付与の権限がありません。", ephemeral=True)
        else:
            await interaction.response.send_message("指定されたロールが見つかりませんでした。", ephemeral=True)

# 使い方（コマンドなどで呼び出し）
# await interaction.channel.send("認証パネル：下のメニューから選んでください", view=RoleSelectView())

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

# Webサーバーを起動
keep_alive()

import os
# ...（中略）...
bot.run(os.getenv("DISCORD_BOT_TOKEN"))

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

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="認証してロールを受け取る", style=discord.ButtonStyle.green)
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # OAuth2のURLを生成
        params = {
            "client_id": "1489974962730307707",
            "redirect_uri": "https://onrender.com",
            "response_type": "code",
            "scope": "identify guilds"
        }
        auth_url = f"https://discord.com?{urllib.parse.urlencode(params)}"
        
        await interaction.response.send_message(
            f"以下のリンクから連携して認証を完了してください：\n[ここをクリックして認証]({auth_url})",
            ephemeral=True
        )

bot = MyBot()

@app.route('/callback')
def callback():
    code = request.args.get('code')

    # 1. トークン取得 (前と同じ)
    data = {
        'client_id': "1489974962730307707",
        'client_secret': "NrjoF90hbFV-SqqaDlKjfrQSRxNjj1gm",
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': "https://onrender.com"
    }
    r = requests.post('https://discord.com', data=data)
    access_token = r.json().get('access_token')

    # 2. ユーザー情報と所属サーバー取得
    headers = {'Authorization': f'Bearer {access_token}'}
    guilds = requests.get('https://discord.com', headers=headers).json()
    user_data = requests.get('https://discord.com', headers=headers).json()
    user_id = int(user_data['id'])

    # 3. 禁止サーバーチェック
    BANNED_ID = "禁止したいサーバーID"
    if any(g['id'] == BANNED_ID for g in guilds):
        return "【認証不可】特定のサーバーに所属しているため認証できません。", 403

    # 4. 決まったロールを一つ付与
    guild = bot.get_guild(1176515964561526914)
    member = guild.get_member(user_id)
    role = guild.get_role(1472220342889218250) # ここにコピーしたIDを貼る

    if member and role:
        bot.loop.create_task(member.add_roles(role))
        return "認証成功！ロールを付与しました。Discordに戻ってください。"
    
    return "ユーザーが見つかりませんでした。", 404

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

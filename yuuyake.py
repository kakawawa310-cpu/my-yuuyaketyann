import discord
from discord import app_commands
from discord.ext import commands
import re
import os
import urllib.parse
import requests
from flask import Flask, request
from threading import Thread

# --- 設定値 ---
CLIENT_ID = "1489974962730307707"
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
# ⚠️ RenderのURLに書き換えてください（例: https://onrender.com）
REDIRECT_URI = "https://my-yuuyaketyann.onrender.com" 

MY_GUILD_ID = 1176515964561526914
VERIFY_ROLE_ID = 1472220342889218250
# ⚠️ 禁止サーバーIDが投稿されるチャンネルID
CHANNEL_ID = 1472220342889218250 

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

@app.route('/callback')
def callback():
    code = request.args.get('code')
    
    data = {
        'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI
    }
    r = requests.post('https://discord.com', data=data)
    access_token = r.json().get('access_token')

    if not access_token:
        return "認証エラー：トークンを取得できませんでした。", 400

    headers = {'Authorization': f'Bearer {access_token}'}
    guilds = requests.get('https://discord.com', headers=headers).json()
    user_data = requests.get('https://discord.com', headers=headers).json()
    user_id = int(user_data['id'])

    # 認証時の禁止鯖チェック（リストにあるIDの鯖にいたら弾く）
    banned_list = [str(gid) for gid in BLACKLIST_GUILD_IDS]
    if any(g['id'] in banned_list for g in guilds):
        return "【認証不可】禁止サーバーに所属しているため、ロールを付与できません。", 403

    guild = bot.get_guild(MY_GUILD_ID)
    member = guild.get_member(user_id)
    role = guild.get_role(VERIFY_ROLE_ID)

    if member and role:
        bot.loop.create_task(member.add_roles(role))
        return "認証成功！ロールを付与しました。Discordに戻ってください。"
    return "サーバーにあなたが見つかりませんでした。", 404

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="認証してロールを受け取る", style=discord.ButtonStyle.green, custom_id="v_btn")
    async def verify(self, interaction, button):
        params = {"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code", "scope": "identify guilds"}
        auth_url = f"https://discord.com?{urllib.parse.urlencode(params)}"
        await interaction.response.send_message(f"連携して認証：\n[ここをクリック]({auth_url})", ephemeral=True)

bot = MyBot()

# --- 招待リンク削除機能のロジック ---
AUTO_DELETE_ENABLED = True
BLACKLIST_GUILD_IDS = set()
INVITE_REGEX = r"(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/([\w\-]+)"

async def update_blacklist():
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        BLACKLIST_GUILD_IDS.clear()
        async for message in channel.history(limit=100):
            if message.content.isdigit():
                BLACKLIST_GUILD_IDS.add(int(message.content))
        print(f"✅ 禁止リスト更新: {BLACKLIST_GUILD_IDS}")

@bot.event
async def on_ready():
    print(f"✅ {bot.user} 起動")
    await update_blacklist()

@bot.event
async def on_message(message):
    global AUTO_DELETE_ENABLED
    if message.author.bot: return

    # 1. 特定チャンネルに数字（ID）が貼られたらリストに追加
    if message.channel.id == CHANNEL_ID and message.content.isdigit():
        BLACKLIST_GUILD_IDS.add(int(message.content))
        print(f"🚫 禁止ID追加: {message.content}")
        return

    # 2. 招待リンクが貼られたら、そのリンク先が禁止リストにあるかチェック
    if AUTO_DELETE_ENABLED:
        match = re.search(INVITE_REGEX, message.content)
        if match:
            invite_code = match.group(3)
            try:
                invite = await bot.fetch_invite(invite_code)
                if invite.guild and invite.guild.id in BLACKLIST_GUILD_IDS:
                    await message.delete()
                    await message.channel.send(f"⚠️ {message.author.mention} 禁止サーバーの招待リンクを削除しました。", delete_after=5)
            except: pass

@bot.tree.command(name="setup_verify", description="認証パネル設置")
async def setup_verify(interaction):
    await interaction.channel.send("【認証】ボタンを押してください。", view=VerifyView())
    await interaction.response.send_message("設置完了", ephemeral=True)

Thread(target=run).start()
bot.run(os.getenv("DISCORD_BOT_TOKEN"))

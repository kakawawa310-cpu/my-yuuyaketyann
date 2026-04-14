import discord
from discord import app_commands
from discord.ext import commands
import re
import os
from flask import Flask, request
from threading import Thread
import urllib.parse
import requests

# --- 設定値 ---
CLIENT_ID = "1489974962730307707"
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
# ⚠️ 下のURLは自分のRenderアプリのドメインに書き換えてください
REDIRECT_URI = "https://my-yuuyaketyann.onrender.com" 
MY_GUILD_ID = 1176515964561526914
VERIFY_ROLE_ID = 1472220342889218250
CHANNEL_ID = 1472220342889218250 # 禁止IDが投稿されるチャンネル

# --- Flask Webサーバー ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

@app.route('/callback')
def callback():
    code = request.args.get('code')
    
    # 1. トークン取得
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    r = requests.post('https://discord.com', data=data, headers=headers)
    token_json = r.json()
    access_token = token_json.get('access_token')

    if not access_token:
        return "エラー: 認証に失敗しました。もう一度やり直してください。", 400

    # 2. ユーザー情報と所属サーバー取得
    auth_headers = {'Authorization': f'Bearer {access_token}'}
    guilds = requests.get('https://discord.com', headers=auth_headers).json()
    user_data = requests.get('https://discord.com', headers=auth_headers).json()
    user_id = int(user_data['id'])

    # 3. 禁止サーバーチェック
    banned_list = [str(gid) for gid in BLACKLIST_GUILD_IDS]
    if any(g['id'] in banned_list for g in guilds):
        return "【認証不可】禁止されているサーバーに所属しているため、ロールを付与できません。", 403

    # 4. ロール付与
    guild = bot.get_guild(MY_GUILD_ID)
    if not guild:
        return "エラー: Botが自分のサーバーにいません。", 500
        
    member = guild.get_member(user_id)
    role = guild.get_role(VERIFY_ROLE_ID)

    if member and role:
        bot.loop.create_task(member.add_roles(role))
        return "認証成功！ロールを付与しました。Discordに戻ってください。"
    
    return "エラー: サーバー内にあなたが見つかりませんでした。先に入室してください。", 404

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- Botの設定 ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True # メンバー操作に必要
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Slash commands synced!")

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="認証してロールを受け取る", style=discord.ButtonStyle.green, custom_id="verify_btn")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        params = {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "identify guilds"
        }
        auth_url = f"https://discord.com?{urllib.parse.urlencode(params)}"
        await interaction.response.send_message(f"以下のリンクから連携して認証を完了してください：\n[ここをクリックして認証]({auth_url})", ephemeral=True)

bot = MyBot()

# --- 判定ロジック ---
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
        print(f"✅ Blacklist updated: {BLACKLIST_GUILD_IDS}")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await update_blacklist()
    # 認証ボタンを設置したいチャンネルで一回だけ実行
    # await bot.get_channel(送信先チャンネルID).send("認証パネル", view=VerifyView())

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id == CHANNEL_ID and message.content.isdigit():
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
            except: pass

@bot.tree.command(name="setup_verify", description="認証用パネルを設置します")
@app_commands.checks.has_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction):
    await interaction.response.send_message("認証パネルを設置しました。", ephemeral=True)
    await interaction.channel.send("【認証】ボタンを押して、禁止サーバーにいないか確認します。", view=VerifyView())

# 起動
Thread(target=run).start()
bot.run(os.getenv("DISCORD_BOT_TOKEN"))

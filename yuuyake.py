import discord
from discord import app_commands
from discord.ext import commands
import re
import os
import urllib.parse
import requests
from flask import Flask, request
from threading import Thread

# --- 設定（定数） ---
CLIENT_ID = "1489974962730307707"
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
# ここのURLがDeveloper Portalの設定と完全に一致している必要があります
REDIRECT_URI = "https://onrender.com"

MY_GUILD_ID = 1176515964561526914
VERIFY_ROLE_ID = 1472220342889218250
CHANNEL_ID = 1472220342889218250 

app = Flask('')

@app.route('/')
def home(): return "Bot is alive!"

@app.route('/callback')
def callback():
    code = request.args.get('code')
    # 1. トークン取得
    data = {
        'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    r = requests.post('https://discord.com', data=data, headers=headers)
    token_json = r.json()
    access_token = token_json.get('access_token')

    if not access_token:
        return f"認証失敗: トークンが取得できませんでした。設定を確認してください。", 400

    # 2. ユーザー情報と所属サーバー取得
    auth_headers = {'Authorization': f'Bearer {access_token}'}
    guilds = requests.get('https://discord.com', headers=auth_headers).json()
    user_data = requests.get('https://discord.com', headers=auth_headers).json()
    user_id = int(user_data['id'])

    # 3. 禁止サーバーチェック（IDリストと照合）
    banned_ids = [str(gid) for gid in BLACKLIST_GUILD_IDS.keys()]
    found_banned = [g['name'] for g in guilds if g['id'] in banned_ids]

    if found_banned:
        return f"【認証拒否】禁止サーバー（{', '.join(found_banned)}）に所属しているため許可されません。", 403

    # 4. ロール付与
    guild = bot.get_guild(MY_GUILD_ID)
    member = guild.get_member(user_id)
    if member:
        bot.loop.create_task(member.add_roles(guild.get_role(VERIFY_ROLE_ID)))
        return "認証に成功しました！ロールを付与しました。Discordに戻ってください。"
    return "サーバーにあなたが見つかりませんでした。先に参加しておいてください。", 404

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
    async def setup_hook(self): await self.tree.sync()

# 76行目の Menu を消して、ここから書き始める
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="認証を開始する", style=discord.ButtonStyle.green, custom_id="verify_fixed_v4")
    async def verify(self, interaction, button):
        params = {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "identify guilds"
        }
        auth_url = f"https://discord.com?{urllib.parse.urlencode(params)}"
        await interaction.response.send_message(f"以下のリンクから連携して認証してください：\n[認証ページへ移動]({auth_url})", ephemeral=True)

# ----------------

bot = MyBot()
SYSTEM_ENABLED = True
BLACKLIST_GUILD_IDS = {} 
INVITE_REGEX = r"(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/([\w\-]+)"

async def update_blacklist():
    channel = bot.get_channel(CHANNEL_ID)
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
    print(f"✅ {bot.user} 起動完了")
    await update_blacklist()

@bot.event
async def on_member_join(member):
    if not SYSTEM_ENABLED: return
    for banned_id, banned_name in BLACKLIST_GUILD_IDS.items():
        banned_guild = bot.get_guild(banned_id)
        if banned_guild and banned_guild.get_member(member.id):
            log_channel = bot.get_channel(CHANNEL_ID)
            if log_channel:
                await log_channel.send(f"⚠️ **入室検知**: {member.mention} が禁止鯖「{banned_name}」に所属しています。")
            break

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id == CHANNEL_ID and message.content.isdigit():
        await update_blacklist()
        return
    if SYSTEM_ENABLED:
        match = re.search(INVITE_REGEX, message.content)
        if match:
            invite_code = match.group(3)
            try:
                invite = await bot.fetch_invite(invite_code)
                if invite.guild and invite.guild.id in BLACKLIST_GUILD_IDS:
                    await message.delete()
                    await message.channel.send(f"⚠️ 禁止サーバーへの招待を削除しました。", delete_after=5)
            except: pass

@bot.tree.command(name="setup_verify", description="認証パネル設置")
async def setup_verify(interaction: discord.Interaction):
    await interaction.channel.send("認証を開始するには下のボタンを押してください。", view=VerifyView())
    await interaction.response.send_message("パネルを設置しました。", ephemeral=True)

@bot.tree.command(name="toggle", description="システムON/OFF")
async def toggle(interaction: discord.Interaction):
    global SYSTEM_ENABLED
    SYSTEM_ENABLED = not SYSTEM_ENABLED
    await interaction.response.send_message(f"システムを {'有効' if SYSTEM_ENABLED else '無効'} にしました。")

Thread(target=run).start()
bot.run(os.getenv("DISCORD_BOT_TOKEN"))

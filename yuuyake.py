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
    data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
    r = requests.post('https://discord.com', data=data)
    access_token = r.json().get('access_token')
    if not access_token: return "認証エラー: トークン取得失敗", 400
    
    headers = {'Authorization': f'Bearer {access_token}'}
    guilds = requests.get('https://discord.com', headers=headers).json()
    user_data = requests.get('https://discord.com', headers=headers).json()
    user_id = int(user_data['id'])
    
    # 認証時の禁止鯖チェック
    banned_keys = [str(gid) for gid in BLACKLIST_GUILD_IDS.keys()]
    if any(g['id'] in banned_keys for g in guilds):
        return "【認証不可】禁止サーバーに所属しているため認証できません。", 403
    
    guild = bot.get_guild(MY_GUILD_ID)
    member = guild.get_member(user_id)
    if member:
        bot.loop.create_task(member.add_roles(guild.get_role(VERIFY_ROLE_ID)))
        return "認証成功！ロールを付与しました。Discordに戻ってください。"
    return "サーバーにあなたが見つかりませんでした。", 404

def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
    async def setup_hook(self): await self.tree.sync()

class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="認証してロールを受け取る", style=discord.ButtonStyle.green, custom_id="verify_button_v1")
    async def verify(self, interaction, button):
        params = {"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code", "scope": "identify guilds"}
        auth_url = f"https://discord.com?{urllib.parse.urlencode(params)}"
        await interaction.response.send_message(f"連携して認証：[ここをクリック]({auth_url})", ephemeral=True)

bot = MyBot()
SYSTEM_ENABLED = True
BLACKLIST_GUILD_IDS = {} # {ID: 名前}
INVITE_REGEX = r"(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/([\w\-]+)"

async def update_blacklist():
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        BLACKLIST_GUILD_IDS.clear()
        messages = [m async for m in channel.history(limit=200)]
        for i, m in enumerate(messages):
            if m.content.isdigit():
                guild_id = int(m.content)
                # 1行上（リスト上は1つ前）を名前として取得
                guild_name = messages[i+1].content if i+1 < len(messages) else "名前不明"
                BLACKLIST_GUILD_IDS[guild_id] = guild_name
        print(f"✅ 禁止リスト更新: {len(BLACKLIST_GUILD_IDS)}件")

@bot.event
async def on_ready():
    print(f"✅ {bot.user} 起動")
    await update_blacklist()

@bot.event
async def on_member_join(member):
    if not SYSTEM_ENABLED: return
    for banned_id, banned_name in BLACKLIST_GUILD_IDS.items():
        banned_guild = bot.get_guild(banned_id)
        if banned_guild and banned_guild.get_member(member.id):
            log_channel = bot.get_channel(CHANNEL_ID)
            if log_channel:
                await log_channel.send(f"⚠️ **禁止鯖所属者検知**\nユーザー: {member.mention} ({member.name})\n該当鯖名: {banned_name}\n鯖ID: {banned_id}")
            break

@bot.event
async def on_message(message):
    if message.author.bot: return
    # ID登録チャンネルでの処理
    if message.channel.id == CHANNEL_ID and message.content.isdigit():
        await update_blacklist()
        return
    # 招待リンク削除
    if SYSTEM_ENABLED:
        match = re.search(INVITE_REGEX, message.content)
        if match:
            invite_code = match.group(3)
            try:
                invite = await bot.fetch_invite(invite_code)
                if invite.guild and invite.guild.id in BLACKLIST_GUILD_IDS:
                    await message.delete()
                    await message.channel.send(f"⚠️ 禁止サーバーの招待を削除しました。", delete_after=5)
            except: pass

@bot.tree.command(name="toggle", description="システムのON/OFF")
@app_commands.checks.has_permissions(administrator=True)
async def toggle(interaction: discord.Interaction):
    global SYSTEM_ENABLED
    SYSTEM_ENABLED = not SYSTEM_ENABLED
    await interaction.response.send_message(f"システムを {'有効' if SYSTEM_ENABLED else '無効'} にしました。")

@bot.tree.command(name="setup_verify", description="認証パネル設置")
async def setup_verify(interaction: discord.Interaction):
    await interaction.channel.send("認証を開始するには下のボタンを押してください。", view=VerifyView())
    await interaction.response.send_message("パネルを設置しました。", ephemeral=True)

Thread(target=run).start()
bot.run(os.getenv("DISCORD_BOT_TOKEN"))

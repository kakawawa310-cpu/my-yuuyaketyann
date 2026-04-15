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
CHANNEL_ID = 1472220342889218250 # 禁止ID・ログ・認証すべて共通のチャンネル

app = Flask('')

@app.route('/')
def home(): return "Bot is alive!"

@app.route('/callback')
def callback():
    code = request.args.get('code')
    data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
    r = requests.post('https://discord.com', data=data)
    access_token = r.json().get('access_token')
    if not access_token: return "認証エラー", 400
    headers = {'Authorization': f'Bearer {access_token}'}
    guilds = requests.get('https://discord.com', headers=headers).json()
    user_data = requests.get('https://discord.com', headers=headers).json()
    user_id = int(user_data['id'])
    
    if any(str(g['id']) in [str(id) for id in BLACKLIST_GUILD_IDS] for g in guilds):
        return "【認証不可】禁止サーバーに所属しています。", 403
    
    guild = bot.get_guild(MY_GUILD_ID)
    member = guild.get_member(user_id)
    if member:
        bot.loop.create_task(member.add_roles(guild.get_role(VERIFY_ROLE_ID)))
        return "認証成功！"
    return "メンバーが見つかりません", 404

def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True # メンバー情報の取得に必須
        intents.presences = False
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self): await self.tree.sync()

bot = MyBot()

# --- 状態管理 ---
SYSTEM_ENABLED = True
BLACKLIST_GUILD_IDS = {} # {サーバーID: サーバー名}
INVITE_REGEX = r"(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/([\w\-]+)"

async def update_blacklist():
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        BLACKLIST_GUILD_IDS.clear()
        messages = [m async for m in channel.history(limit=200)]
        for i, m in enumerate(messages):
            if m.content.isdigit():
                guild_id = int(m.content)
                # 1つ上のメッセージをサーバー名として取得
                guild_name = messages[i+1].content if i+1 < len(messages) else "不明なサーバー"
                BLACKLIST_GUILD_IDS[guild_id] = guild_name
        print(f"✅ 禁止リスト更新: {len(BLACKLIST_GUILD_IDS)}件")

@bot.event
async def on_ready():
    print(f"✅ {bot.user} 起動")
    await update_blacklist()

@bot.event
async def on_member_join(member):
    """新規参加時のチェック（Botが入っているサーバーなら検知可能）"""
    if not SYSTEM_ENABLED: return
    
    for banned_id, banned_name in BLACKLIST_GUILD_IDS.items():
        # Botが共通で入っているサーバーの所属を確認
        banned_guild = bot.get_guild(banned_id)
        if banned_guild and banned_guild.get_member(member.id):
            log_channel = bot.get_channel(CHANNEL_ID)
            if log_channel:
                await log_channel.send(
                    f"⚠️ **禁止サーバー所属者を検知**\n"
                    f"ユーザー: {member.mention} ({member.name})\n"
                    f"該当サーバー名: {banned_name}\n"
                    f"サーバーID: {banned_id}"
                )
            break

@bot.event
async def on_message(message):
    global SYSTEM_ENABLED
    if message.author.bot: return

    # ID登録（数字のみの場合）
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
                    await message.channel.send(f"⚠️ {message.author.mention} 禁止サーバーの招待リンクを削除しました。", delete_after=5)
            except: pass

# --- コマンド ---
@bot.tree.command(name="toggle", description="システムのON/OFFを切り替えます")
@app_commands.checks.has_permissions(administrator=True)
async def toggle(interaction: discord.Interaction):
    global SYSTEM_ENABLED
    SYSTEM_ENABLED = not SYSTEM_ENABLED
    status = "有効" if SYSTEM_ENABLED else "無効"
    await interaction.response.send_message(f"システムを **{status}** にしました。")

@bot.tree.command(name="setup_verify", description="認証パネル設置")
async def setup_verify(interaction: discord.Interaction):
    await interaction.channel.send("【認証】ボタンを押してください。", view=VerifyView())
    await interaction.response.send_message("設置完了", ephemeral=True)

class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="認証", style=discord.ButtonStyle.green, custom_id="v_btn")
    async def verify(self, interaction, button):
        params = {"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code", "scope": "identify guilds"}
        auth_url = f"https://discord.com?{urllib.parse.urlencode(params)}"
        await interaction.response.send_message(f"連携して認証：[ここをクリック]({auth_url})", ephemeral=True)

Thread(target=run).start()
bot.run(os.getenv("DISCORD_BOT_TOKEN"))

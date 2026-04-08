import discord
from discord import app_commands
from discord.ext import commands
import os, json, re
from flask import Flask
from threading import Thread

# --- 設定保存機能 ---
CONFIG_FILE = "config.json"
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f: return json.load(f)
    return {
        "log_channel_id": None, 
        "verify_role_id": None, 
        "invite_anti_link": True,
        "blacklist_source_channel_id": 1472220342889218250  # ←ここに「IDが書かれたチャンネル」のIDを入れる
    }

# --- Render用Webサーバー ---
app = Flask('')
@app.route('/')
def home(): return "Bot is alive!"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
def keep_alive(): Thread(target=run, daemon=True).start()

# --- 認証ボタンのUI ---
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="認証する", style=discord.ButtonStyle.green, custom_id="verify_btn")
    async def verify(self, interaction: discord.Interaction):
        blacklisted_names = []
        for g_id in WATCH_GUILDS:
            guild = interaction.client.get_guild(g_id)
            if guild and guild.get_member(interaction.user.id):
                blacklisted_names.append(guild.name)

        if blacklisted_names:
            await interaction.response.send_message(f"❌ 指定サーバー（{', '.join(blacklisted_names)}）に参加しているため認証できません。", ephemeral=True)
            try:
                await interaction.user.kick(reason="ブラックリストサーバー参加による認証拒否")
                await send_log(interaction.client, f"👤 {interaction.user.mention} をキックしました（認証拒否: {', '.join(blacklisted_names)}に在籍）")
            except: pass
            return

        role_id = config_data.get("verify_role_id")
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role:
                await interaction.user.add_roles(role)
                await interaction.response.send_message("✅ 認証に成功しました！", ephemeral=True)
                await send_log(interaction.client, f"✅ {interaction.user.mention} が認証を完了しました。")
            else:
                await interaction.response.send_message("⚠️ ロールが見つかりません。", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ 認証ロールが設定されていません。", ephemeral=True)

async def send_log(bot, message):
    log_id = config_data.get("log_channel_id")
    if log_id:
        channel = bot.get_channel(log_id)
        if channel: await channel.send(message)

# --- Bot本体 ---
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())

    async def setup_hook(self):
        self.add_view(VerifyView())
        await self.tree.sync()

bot = MyBot()

@bot.event
async def on_ready():
    activity = discord.Activity(type=discord.ActivityType.watching, name="ゆねっさむの歌声")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    print('お問い合わせは、宣伝茶亭のさぴょにゃんへ！')

# 参加時の自動キック
@bot.event
async def on_member_join(member):
    for g_id in WATCH_GUILDS:
        guild = bot.get_guild(g_id)
        if guild and guild.get_member(member.id):
            try:
                await member.kick(reason="ブラックリストサーバー参加")
                await send_log(bot, f"🚨 {member.mention} を自動キックしました（参加時チェック: {guild.name}に在籍）")
            except: pass
            break

# 1. 認証パネルとログ設定
@bot.tree.command(name="setup_verify", description="認証パネル設置・ロール・ログチャンネルを一括設定します")
@app_commands.describe(role="付与するロール", log_channel="ログ用チャンネル")
async def setup_verify(interaction: discord.Interaction, role: discord.Role, log_channel: discord.TextChannel):
    config_data["verify_role_id"] = role.id
    config_data["log_channel_id"] = log_channel.id
    save_config(config_data)
    embed = discord.Embed(title="✅ 認証パネル", description="下のボタンを押して認証してください。\n※対象サーバーにいる場合は自動でキックされます。", color=0x2ecc71)
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message("✅ 設置と設定が完了しました！", ephemeral=True)

# 2. 招待リンク無効化のON/OFF設定
@bot.tree.command(name="toggle_anti_invite", description="招待リンクの自動無効化をON/OFFします")
@app_commands.choices(setting=[
    app_commands.Choice(name="ON (有効)", value=1),
    app_commands.Choice(name="OFF (無効)", value=0)
])
async def toggle_anti_invite(interaction: discord.Interaction, setting: int):
    config_data["invite_anti_link"] = bool(setting)
    save_config(config_data)
    status = "ON" if setting else "OFF"
    await interaction.response.send_message(f"✅ 招待リンク自動無効化を **{status}** にしました。", ephemeral=True)
    await send_log(bot, f"⚙️ 設定変更: 招待無効化機能が **{status}** になりました。")

# 招待リンク監視
@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None: return
    
    # 招待無効化機能がON、かつ監視対象サーバーの場合
    if config_data.get("invite_anti_link") and message.guild.id in WATCH_GUILDS:
        codes = re.findall(r'(?:discord\.gg/|discord\.com/invite/)([\w-]+)', message.content)
        for code in codes:
            try:
                invite = await bot.fetch_invite(code)
                if invite.guild.id in [g.id for g in bot.guilds]:
                    await invite.delete(reason="自動無効化設定により削除")
                    await send_log(bot, f"🔗 自鯖招待を無効化しました: {code} (場所: {message.guild.name})")
            except: pass
    
    await bot.process_commands(message)

if __name__ == "__main__":
    keep_alive()
    bot.run(os.environ.get("TOKEN"))

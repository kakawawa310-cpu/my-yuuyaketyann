import discord
from discord import app_commands
from discord.ext import commands
import os, json, re
from flask import Flask
from threading import Thread

# --- 設定保存機能 ---
CONFIG_FILE = "config.json"
SOURCE_CHANNEL_ID = 1472220342889218250  # IDを読み取るチャンネルを固定

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f: return json.load(f)
    return {
        "log_channel_id": None, 
        "verify_role_id": None, 
        "invite_anti_link": True
    }

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

config_data = load_config()

# --- ID自動読み取り関数 (指定チャンネル固定) ---
async def get_watch_guilds(bot):
    channel = bot.get_channel(SOURCE_CHANNEL_ID)
    if not channel: return []
    
    guild_ids = []
    # 直近100件のメッセージからID（数字）を抽出
    async for message in channel.history(limit=100):
        found = re.findall(r'\d{17,20}', message.content)
        guild_ids.extend([int(i) for i in found])
    return list(set(guild_ids))

# --- Render用サーバー ---
app = Flask('')
@app.route('/')
def home(): return "Bot is alive!"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
def keep_alive(): Thread(target=run, daemon=True).start()

# --- 認証ボタンUI ---
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="認証する", style=discord.ButtonStyle.green, custom_id="verify_btn")
    async def verify(self, interaction: discord.Interaction):
        watch_list = await get_watch_guilds(interaction.client)
        blacklisted_names = []
        
        # ユーザーが監視対象サーバーにいるかチェック
        for g_id in watch_list:
            guild = interaction.client.get_guild(g_id)
            if guild and guild.get_member(interaction.user.id):
                blacklisted_names.append(guild.name)

        if blacklisted_names:
            await interaction.response.send_message(f"❌ 対象サーバーに参加しているため認証できません。", ephemeral=True)
            try:
                await interaction.user.kick(reason="ブラックリストサーバー参加による拒否")
                await send_log(interaction.client, f"👤 {interaction.user.mention} をキックしました（認証拒否: {', '.join(blacklisted_names)} に在籍）")
            except: pass
            return

        # 認証成功：ロール付与
        role_id = config_data.get("verify_role_id")
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role:
                await interaction.user.add_roles(role)
                await interaction.response.send_message("✅ 認証に成功しました！", ephemeral=True)
                await send_log(interaction.client, f"✅ {interaction.user.mention} が認証を完了しました。")
            else:
                await interaction.response.send_message("⚠️ ロールが見つかりません。設定を確認してください。", ephemeral=True)
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

# メンバー参加時の自動キック
@bot.event
async def on_member_join(member):
    watch_list = await get_watch_guilds(bot)
    for g_id in watch_list:
        guild = bot.get_guild(g_id)
        if guild and guild.get_member(member.id):
            try:
                await member.kick(reason="ブラックリストサーバー参加")
                await send_log(bot, f"🚨 {member.mention} を自動キックしました（在籍: {guild.name}）")
            except: pass
            break

# 1. 認証パネル設置と設定 (blacklist_channelの設定を削除)
@bot.tree.command(name="setup_verify", description="認証パネル設置とロール・ログ設定を一括で行います")
async def setup_verify(interaction: discord.Interaction, role: discord.Role, log_channel: discord.TextChannel):
    config_data["verify_role_id"] = role.id
    config_data["log_channel_id"] = log_channel.id
    save_config(config_data)
    
    embed = discord.Embed(title="✅ 認証パネル", description="下のボタンを押して認証を完了してください。\n※対象サーバーにいる場合は自動でキックされます。", color=0x2ecc71)
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message(f"✅ 設定を保存しました！（監視元: <#{SOURCE_CHANNEL_ID}>）", ephemeral=True)

# 2. 招待リンク無効化設定
@bot.tree.command(name="toggle_anti_invite", description="招待リンク無効化のON/OFF")
@app_commands.choices(setting=[app_commands.Choice(name="ON", value=1), app_commands.Choice(name="OFF", value=0)])
async def toggle_anti_invite(interaction: discord.Interaction, setting: int):
    config_data["invite_anti_link"] = bool(setting)
    save_config(config_data)
    await interaction.response.send_message(f"✅ 招待リンク自動無効化を {'ON' if setting else 'OFF'} にしました。", ephemeral=True)

# 招待リンク監視
@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None: return
    
    if config_data.get("invite_anti_link"):
        watch_list = await get_watch_guilds(bot)
        if message.guild.id in watch_list:
            codes = re.findall(r'(?:discord\.gg/|discord\.com/invite/)([\w-]+)', message.content)
            for code in codes:
                try:
                    invite = await bot.fetch_invite(code)
                    # 招待のリンク先がBotの参加しているいずれかのサーバーなら削除
                    if invite.guild.id in [g.id for g in bot.guilds]:
                        await invite.delete(reason="自動無効化")
                        await send_log(bot, f"🔗 自鯖招待を無効化しました: {code} (場所: {message.guild.name})")
                except: pass
    
    await bot.process_commands(message)

if __name__ == "__main__":
    keep_alive()
    bot.run(os.environ.get("TOKEN"))

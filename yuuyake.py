import discord
from discord import app_commands
from discord.ext import commands
import os, json, re
from flask import Flask
from threading import Thread

# --- 設定保存機能 ---
CONFIG_FILE = "config.json"
SOURCE_CHANNEL_ID = 1472220342889218250  # IDを読み取るチャンネル

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

# --- ID自動読み取り関数 ---
async def get_watch_guilds(bot):
    channel = bot.get_channel(SOURCE_CHANNEL_ID)
    if not channel: return []
    guild_ids = []
    async for message in channel.history(limit=100):
        found = re.findall(r'\d{17,20}', message.content)
        guild_ids.extend([int(i) for i in found])
    return list(set(guild_ids))

# --- Render用Webサーバー ---
app = Flask('')
@app.route('/')
def home(): return "Bot is alive!"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
def keep_alive(): Thread(target=run, daemon=True).start()

# --- 認証ボタンUI (3秒制限対策済み) ---
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="認証する", style=discord.ButtonStyle.green, custom_id="verify_btn")
    async def verify(self, interaction: discord.Interaction):
        # 3秒制限を回避するために保留状態にする
        await interaction.response.defer(ephemeral=True)

        watch_list = await get_watch_guilds(interaction.client)
        blacklisted_names = []
        
        for g_id in watch_list:
            guild = interaction.client.get_guild(g_id)
            if guild and guild.get_member(interaction.user.id):
                blacklisted_names.append(guild.name)

        if blacklisted_names:
            await interaction.followup.send(f"❌ 対象サーバー（{', '.join(blacklisted_names)}）に参加しているため認証できません。退出してから再度お試しください。", ephemeral=True)
            await send_log(interaction.client, f"⚠️ {interaction.user.mention} の認証をブロックしました（在籍: {', '.join(blacklisted_names)}）")
            return

        role_id = config_data.get("verify_role_id")
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role:
                try:
                    await interaction.user.add_roles(role)
                    await interaction.followup.send("✅ 認証に成功しました！", ephemeral=True)
                    await send_log(interaction.client, f"✅ {interaction.user.mention} が認証を完了しました。")
                except discord.Forbidden:
                    await interaction.followup.send("❌ ロール付与権限がありません。Botの順位をサーバー設定で上げてください。", ephemeral=True)
            else:
                await interaction.followup.send("⚠️ ロールが見つかりません。", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ 認証ロールが未設定です。", ephemeral=True)

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
    print('起動完了：お問い合わせは、宣伝茶亭のさぴょにゃんへ！')

# 1. 認証パネル設置コマンド
@bot.tree.command(name="setup_verify", description="認証パネル設置とロール・ログ設定")
async def setup_verify(interaction: discord.Interaction, role: discord.Role, log_channel: discord.TextChannel):
    config_data["verify_role_id"] = role.id
    config_data["log_channel_id"] = log_channel.id
    save_config(config_data)
    embed = discord.Embed(title="✅ 認証パネル", description="ボタンを押して認証してください。\n※対象サーバーにいる場合は認証できません。", color=0x3498db)
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message(f"✅ 設定完了（監視元: <#{SOURCE_CHANNEL_ID}>）", ephemeral=True)

# 2. 招待リンク無効化ON/OFF
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
                    if invite.guild.id in [g.id for g in bot.guilds]:
                        await invite.delete(reason="自動無効化")
                        await send_log(bot, f"🔗 招待を無効化しました: {code} (場所: {message.guild.name})")
                except: pass
    await bot.process_commands(message)

if __name__ == "__main__":
    keep_alive()
    bot.run(os.environ.get("TOKEN"))

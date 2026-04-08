import discord
from discord import app_commands
from discord.ext import commands
import os, json, re, asyncio
from flask import Flask
from threading import Thread

# --- 設定保存機能 ---
CONFIG_FILE = "config.json"
SOURCE_CHANNEL_ID = 1472220342889218250  # 監視対象サーバーIDを読み取るチャンネル

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f: return json.load(f)
    return {
        "log_channel_id": None, 
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

async def send_log(bot, message):
    log_id = config_data.get("log_channel_id")
    if log_id:
        channel = bot.get_channel(log_id)
        if channel: await channel.send(message)

# --- Bot本体 ---
class MyBot(commands.Bot):
    def __init__(self):
        # メッセージ削除のために全てのIntentsを有効化
        super().__init__(command_prefix="!", intents=discord.Intents.all())
    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()

@bot.event
async def on_ready():
    activity = discord.Activity(type=discord.ActivityType.watching, name="ゆねっさむの歌声")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    print('起動完了：お問い合わせは、宣伝茶亭のさぴょにゃんへ！')

# --- 新機能：退出した人のメッセージを自動削除 ---
@bot.event
async def on_member_remove(member):
    count = 0
    # サーバー内の全テキストチャンネルをスキャン（Botが閲覧できる範囲）
    for channel in member.guild.text_channels:
        try:
            # 直近100件のメッセージから退出者のものを探して削除
            deleted = await channel.purge(limit=100, check=lambda m: m.author.id == member.id)
            count += len(deleted)
        except discord.Forbidden:
            continue # 権限がないチャンネルはスキップ
        except Exception as e:
            print(f"削除エラー: {e}")

    if count > 0:
        await send_log(bot, f"🗑️ {member.mention} さんのメッセージを計 {count} 件削除完了しました。")
    else:
        await send_log(bot, f"👤 {member.mention} さんが退出しましたが、削除対象のメッセージは見つかりませんでした。")

# --- 設定用コマンド ---
@bot.tree.command(name="setup_logs", description="ログを送信するチャンネルを設定します")
async def setup_logs(interaction: discord.Interaction, log_channel: discord.TextChannel):
    config_data["log_channel_id"] = log_channel.id
    save_config(config_data)
    await interaction.response.send_message(f"✅ ログチャンネルを {log_channel.mention} に設定しました。", ephemeral=True)

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

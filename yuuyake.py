import discord
from discord.ext import commands
from discord import app_commands
import random
import os
import re
from flask import Flask
from threading import Thread

# --- Render用: Webサーバー ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running!"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive():
    t = Thread(target=run)
    t.start()

# --- データ・確率設定 ---
GACHA_DATA = {
    "UR": {"prob": 3, "items": ["🔥神焔の騎士", "❄️絶対零度の魔女"]},
    "SSR": {"prob": 7, "items": ["⚔️勇者の剣", "🛡️伝説の盾"]},
    "SR": {"prob": 20, "items": ["🏹熟練の弓兵", "🧪魔力の雫"]},
    "R": {"prob": 70, "items": ["🗡️見習い剣士", "🍞回復パン"]}
}
SUMMON_DATA = {
    "UR": {"prob": 3, "items": ["🐉創世竜バハムート", "😇大天使ミカエル"]},
    "SSR": {"prob": 7, "items": ["🦁キングキマイラ", "🔥フェニックス"]},
    "SR": {"prob": 20, "items": ["🐺人狼", "🌑シャドウナイト"]},
    "R": {"prob": 70, "items": ["🟢スライム", "💀スケルトン"]}
}

# --- Bot初期設定 ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# サーバーごとの設定保存用
server_settings = {} 
# 構造例: {guild_id: {"gacha": bool, "summon": bool, "anti_invite": bool, "target_user_id": int, "log_channel_id": int}}

def get_settings(guild_id):
    return server_settings.get(guild_id, {"gacha": False, "summon": False, "anti_invite": False, "target_user_id": None, "log_channel_id": None})

# --- コロシアム View ---
class ColiseumView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="⚔️ 参戦", style=discord.ButtonStyle.danger, custom_id="join_battle")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = get_settings(interaction.guild_id)
        
        # 特定ユーザーの参戦通知
        if settings["target_user_id"] == interaction.user.id and settings["log_channel_id"]:
            log_chan = interaction.guild.get_channel(settings["log_channel_id"])
            if log_chan:
                await log_chan.send(f"📢 注目！特定ユーザー {interaction.user.mention} がコロシアムに参戦しました！")

        result = random.choice(["勝利！🎉", "敗北...💀"])
        await interaction.response.send_message(f"{interaction.user.mention} の対戦結果: **{result}**", ephemeral=False)

# --- スラッシュコマンド ---

@bot.tree.command(name="roulette_mode", description="ガチャと召喚の有効/無効を設定")
@app_commands.choices(mode=[
    app_commands.Choice(name="ガチャのみ", value="gacha"),
    app_commands.Choice(name="召喚のみ", value="summon"),
    app_commands.Choice(name="両方", value="both"),
    app_commands.Choice(name="解除", value="off"),
])
async def roulette_mode(interaction: discord.Interaction, mode: str):
    settings = get_settings(interaction.guild_id)
    if mode == "gacha": settings.update({"gacha": True, "summon": False})
    elif mode == "summon": settings.update({"gacha": False, "summon": True})
    elif mode == "both": settings.update({"gacha": True, "summon": True})
    else: settings.update({"gacha": False, "summon": False})
    
    server_settings[interaction.guild_id] = settings
    await interaction.response.send_message(f"ルーレット設定を「{mode}」に変更しました。")

@bot.tree.command(name="config_notify", description="特定ユーザーの参戦をログに通知する設定")
async def config_notify(interaction: discord.Interaction, user_id: str, log_channel: discord.TextChannel):
    settings = get_settings(interaction.guild_id)
    settings.update({"target_user_id": int(user_id), "log_channel_id": log_channel.id})
    server_settings[interaction.guild_id] = settings
    await interaction.response.send_message(f"ID:{user_id} の参戦通知を {log_channel.mention} に設定しました。")

@bot.tree.command(name="config_antidiscord", description="招待URLの自動削除設定")
@app_commands.choices(status=[
    app_commands.Choice(name="有効", value="on"),
    app_commands.Choice(name="無効", value="off"),
])
async def config_antidiscord(interaction: discord.Interaction, status: str):
    settings = get_settings(interaction.guild_id)
    settings["anti_invite"] = (status == "on")
    server_settings[interaction.guild_id] = settings
    await interaction.response.send_message(f"招待URL自動削除を「{status}」にしました。")

@bot.tree.command(name="setup_coliseum", description="指定したチャンネルに募集パネルを設置")
async def setup_coliseum(interaction: discord.Interaction, channel: discord.TextChannel):
    embed = discord.Embed(title="🏟️ コロシアム開催", description="参戦ボタンを押してください！", color=0xff0000)
    await channel.send(embed=embed, view=ColiseumView())
    await interaction.response.send_message(f"{channel.mention} にパネルを設置。", ephemeral=True)

# --- イベント処理 ---
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    settings = get_settings(message.guild.id)

    # 招待URL削除機能 (discord.gg/...)
    if settings["anti_invite"]:
        if re.search(r'(discord.gg/|://discord.com)', message.content):
            await message.delete()
            await message.channel.send(f"{message.author.mention} 招待URLの送信は禁止されています。", delete_after=5)
            return

    # ガチャ・召喚反応
    if message.content == "ガチャ" and settings["gacha"]:
        rarity = random.choices(list(GACHA_DATA.keys()), weights=[d["prob"] for d in GACHA_DATA.values()])[0]
        item = random.choice(GACHA_DATA[rarity]["items"])
        await message.reply(f"【{rarity}】✨ {item} ✨")
    
    if message.content == "召喚" and settings["summon"]:
        rarity = random.choices(list(SUMMON_DATA.keys()), weights=[d["prob"] for d in SUMMON_DATA.values()])[0]
        item = random.choice(SUMMON_DATA[rarity]["items"])
        await message.reply(f"【{rarity}】🌀 {item} 🌀")

    await bot.process_commands(message)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in: {bot.user}")

keep_alive()
bot.run(os.getenv("DISCORD_BOT_TOKEN"))

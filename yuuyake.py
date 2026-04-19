import discord
import random
import os
import re
from discord.ext import commands
from discord import app_commands
from flask import Flask
from threading import Thread

# Renderのポート監視をパスするためのダミーサーバー
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    # Renderは環境変数 PORT を指定してくるので、それに合わせる
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True # Botが終了したときに一緒に終了するようにする
    t.start()

# --- 設定データ ---
GACHA_TABLE = {
    "SSR": (["[極] 聖騎士アーサー", "[極] 闇の魔導師"], 3),
    "SR":  (["伝説の剣", "守護者の鎧", "癒やしの杖"], 12),
    "R":   (["鋼の剣", "鉄の盾", "魔力の小瓶"], 35),
    "N":   (["ひのきのぼう", "布の服", "ただの石"], 50)
}

SUMMON_TABLE = {
    "SSR": (["神獣フェニックス", "冥王ハデス"], 1),
    "SR":  (["ワイバーン", "エルフの弓兵"], 9),
    "R":   (["オーク", "ゴブリンリーダー"], 30),
    "N":   (["スライム", "コウモリ"], 60)
}

def pull_lottery(table):
    rarities = list(table.keys())
    weights = [data[1] for data in table.values()]
    chosen_rarity = random.choices(rarities, weights=weights)[0]
    item = random.choice(table[chosen_rarity][0])
    return chosen_rarity, item

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True # メッセージの内容を読み取るために必須
        super().__init__(command_prefix="!", intents=intents)
        self.channel_configs = {} # {channel_id: mode}

    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()

# --- 設定用スラッシュコマンド ---
@bot.tree.command(name="config", description="このチャンネルの機能を設定します")
@app_commands.choices(mode=[
    app_commands.Choice(name="ガチャのみ", value="gacha"),
    app_commands.Choice(name="召喚のみ", value="summon"),
    app_commands.Choice(name="両方", value="both"),
    app_commands.Choice(name="解除", value="none")
])
async def config(interaction: discord.Interaction, mode: str):
    bot.channel_configs[interaction.channel_id] = mode
    mode_text = {"gacha": "ガチャ", "summon": "召喚", "both": "ガチャ＆召喚", "none": "解除"}[mode]
    await interaction.response.send_message(f"✅ 設定完了: このチャンネルは **{mode_text}** モードになりました。")

# --- メッセージ反応セクション ---
@bot.event
async def on_message(message):
    if message.author.bot: return

    # 1. 招待リンク監視 (前回の機能)
    LOG_CHANNEL_ID = 1472220342889218250
    SOURCE_GUILD_ID = 1176515964561526914
    
    if "discord.gg/" in message.content or "discord.com/invite/" in message.content:
        invites = re.findall(r'(?:discord\.gg/|discord\.com/invite/)([\w-]+)', message.content)
        for code in invites:
            try:
                invite = await bot.fetch_invite(code)
                if invite.guild and invite.guild.id == SOURCE_GUILD_ID:
                    await message.delete()
                    log_ch = bot.get_channel(LOG_CHANNEL_ID)
                    if log_ch:
                        await log_ch.send(f"🚫 **招待削除**: {message.author.mention} が {invite.guild.name} & {SOURCE_GUILD_ID} の招待を貼ったため削除しました。")
            except: continue

    # 2. ガチャ・召喚の単語反応
    mode = bot.channel_configs.get(message.channel.id, "none")
    
    # ガチャに反応
    if "ガチャ" in message.content:
        if mode in ["gacha", "both"]:
            rarity, item = pull_lottery(GACHA_TABLE)
            color = 0xffd700 if rarity == "SSR" else 0xadd8e6
            embed = discord.Embed(title="🎲 ガチャ結果", description=f"{message.author.mention}さんの結果\n**[{rarity}]** {item}", color=color)
            await message.channel.send(embed=embed)
        elif mode != "none": # モード設定はあるがガチャが許可されていない場合
            pass 

    # 召喚に反応
    if "召喚" in message.content:
        if mode in ["summon", "both"]:
            rarity, item = pull_lottery(SUMMON_TABLE)
            embed = discord.Embed(title="🪄 召喚完了", description=f"{message.author.mention}が呼び出した！\n**[{rarity}]** {item}", color=0x9400d3)
            await message.channel.send(embed=embed)

    await bot.process_commands(message)

# --- 入室監視 ---
@bot.event
async def on_member_join(member):
    SOURCE_GUILD_ID = 1176515964561526914
    LOG_CHANNEL_ID = 1472220342889218250
    source_guild = bot.get_guild(SOURCE_GUILD_ID)
    if source_guild:
        target_user = source_guild.get_member(member.id)
        if target_user:
            log_ch = bot.get_channel(LOG_CHANNEL_ID)
            if log_ch:
                await log_ch.send(f"⚠️ **入室通知**: {member.mention} は 「{source_guild.name} & {SOURCE_GUILD_ID}」 に参加しているユーザーです。")

if __name__ == "__main__":
    # Webサーバーを起動
    keep_alive()
    
    # Botを起動
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    bot.run(TOKEN)

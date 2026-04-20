import discord
import random
import os
import re
from discord.ext import commands
from discord import app_commands
from flask import Flask
from threading import Thread
import json

# --- ダミーサーバー設定 ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# --- ガチャデータ ---
SETTING_FILE = "forward_settings.json"

# 2. 起動時にファイルから読み込む関数
def load_settings():
    if os.path.exists(SETTING_FILE):
        with open(SETTING_FILE, "r") as f:
            return json.load(f)
    return {}

# 3. 設定をファイルに書き込む関数
def save_settings(settings):
    with open(SETTING_FILE, "w") as f:
        json.dump(settings, f)

forward_settings = load_settings()

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

# --- Botクラス定義 ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        
        # 設定保存用
        self.channel_configs = {}  # {channel_id: mode}
        self.log_channel_id = None # ログ出力先
        self.anti_invite = False   # 招待削除の有効化フラグ
        self.source_guild_id = 1176515964561526914 # 監視対象サーバーID

    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()

# --- 管理設定コマンド ---

# 送り先（ペースト先）のチャンネルIDを固定
DEST_CHANNEL_ID = 1495747010802876528 

@bot.command()
async def set_source(ctx, source: discord.TextChannel):
    """コピー元（送り元）を登録する"""
    bot.forward_settings[str(source.id)] = DEST_CHANNEL_ID
    save_settings(bot.forward_settings)
    await ctx.send(f"監視開始：{source.mention} の投稿を固定チャンネルへ転送します。")
    # ここにあった await bot.process_commands(message) は削除しました（コマンド内では不要なため）

# --- メッセージ受信イベント ---

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # 登録された「送り元」リストにあるか確認
    if str(message.channel.id) in bot.forward_settings:
        dest_id = bot.forward_settings[str(message.channel.id)]
        dest_channel = bot.get_channel(dest_id)
        if dest_channel:
            await dest_channel.send(f"{message.author.display_name}: {message.content}")

    # 他のコマンド（!set_sourceなど）を動かすために必須
    await bot.process_commands(message)
    
@bot.tree.command(name="setup_admin", description="管理用ログチャンネルと招待削除の有無を設定します")
@app_commands.describe(channel="ログを出力するチャンネル", anti_invite="招待リンクを削除するかどうか")
async def setup_admin(interaction: discord.Interaction, channel: discord.TextChannel, anti_invite: bool):
    # 本来は管理者権限チェックを入れるのが望ましい
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ このコマンドは管理者のみ実行できます。", ephemeral=True)
        return

    bot.log_channel_id = channel.id
    bot.anti_invite = anti_invite
    
    status = "有効" if anti_invite else "無効"
    await interaction.response.send_message(
        f"✅ 設定を更新しました。\n"
        f"**ログチャンネル:** {channel.mention}\n"
        f"**招待リンク自動削除:** {status}"
    )

# --- ガチャ設定コマンド ---
@bot.tree.command(name="config", description="このチャンネルのガチャ/召喚機能を設定します")
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

    # 1. 招待リンク監視 (フラグがTrueかつログチャンネルが設定されている場合のみ動作)
    if bot.anti_invite and bot.log_channel_id:
        if "discord.gg/" in message.content or "discord.com/invite/" in message.content:
            invites = re.findall(r'(?:discord\.gg/|discord\.com/invite/)([\w-]+)', message.content)
            for code in invites:
                try:
                    invite = await bot.fetch_invite(code)
                    if invite.guild and invite.guild.id == bot.source_guild_id:
                        await message.delete()
                        log_ch = bot.get_channel(bot.log_channel_id)
                        if log_ch:
                            await log_ch.send(f"🚫 **招待削除**: {message.author.mention} が禁止サーバーの招待を貼ったため削除しました。")
                except: continue

    # 2. ガチャ・召喚の反応
    mode = bot.channel_configs.get(message.channel.id, "none")
    
    if "ガチャ" in message.content and mode in ["gacha", "both"]:
        rarity, item = pull_lottery(GACHA_TABLE)
        color = 0xffd700 if rarity == "SSR" else 0xadd8e6
        embed = discord.Embed(title="🎲 ガチャ結果", description=f"{message.author.mention}さんの結果\n**[{rarity}]** {item}", color=color)
        await message.channel.send(embed=embed)

    if "召喚" in message.content and mode in ["summon", "both"]:
        rarity, item = pull_lottery(SUMMON_TABLE)
        embed = discord.Embed(title="🪄 召喚完了", description=f"{message.author.mention}が呼び出した！\n**[{rarity}]** {item}", color=0x9400d3)
        await message.channel.send(embed=embed)

    await bot.process_commands(message)

# --- 入室監視 ---
@bot.event
async def on_member_join(member):
    if bot.log_channel_id:
        source_guild = bot.get_guild(bot.source_guild_id)
        if source_guild:
            # Botがそのサーバーに参加していないとget_memberはNoneを返す可能性があるため注意
            target_user = source_guild.get_member(member.id)
            if target_user:
                log_ch = bot.get_channel(bot.log_channel_id)
                if log_ch:
                    await log_ch.send(f"⚠️ **入室通知**: {member.mention} は 「{source_guild.name}」 に参加しているユーザーです。")

if __name__ == "__main__":
    keep_alive()
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    bot.run(TOKEN)

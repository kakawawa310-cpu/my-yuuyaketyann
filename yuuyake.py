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
# 誰が誰をコピーしているかを保持（実行中のメモリ用）
# {設定した人のID: コピーされた人のID}
user_copy_map = {} 
parent_vcs = {}

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
# --- あなたの読み上げ関数の中 ---
async def 読み上げ関数名(message):
    # 1. 誰の声を使うか判定
    speaker_id = user_copy_map.get(message.author.id, message.author.id)

    # 2. ここをあなたのコードの変数名に合わせてください！
    # もし設定データが 'self.config' なら、self.config.get(...) にします
    voice_config = voice_db.get(str(speaker_id))  
    
    if not voice_config:
        voice_config = return.get(str(message.author.id))

# --- Botクラス定義 ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        
        # ↓↓↓ この行を追加してください（super().__init__より下であればOK）
        self.forward_settings = load_settings() 

        self.channel_configs = {}  # ここから下は既存のコード
        self.log_channel_id = None
        self.anti_invite = False   # 招待削除の有効化フラグ
        self.source_guild_id = 1176515964561526914 # 監視対象サーバーID

    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()

@bot.event
async def on_message(message):
    if message.author.bot: return

    # コピー対象がいればその人のID、いなければ発言者本人のIDを使う
    speaker_id = user_copy_map.get(message.author.id, message.author.id)

    # 【ここにあなたの既存の読み上げ処理を繋げます】
    # 例：既存の読み上げ機能が「speaker_id」の設定を使って喋るように書く
    
    await bot.process_commands(message)
    
@bot.event  # ← ここが client になっていませんか？
async def on_voice_state_update(member, before, after):
    # parent_vcs が関数の外にあるので、ここはこのままでOK
    parent_id = parent_vcs.get(member.guild.id)
    
    if after.channel and after.channel.id == parent_id:
        target_id = user_copy_map.get(member.id, member.id)
        target = member.guild.get_member(target_id) or member
        
        category = discord.utils.get(member.guild.categories, name="グローバルボイス")
        
        new_vc = await member.guild.create_voice_channel(
            name=f"👥 {target.display_name} のコピー",
            category=category
        )
        await member.move_to(new_vc)

    if before.channel and "👥" in before.channel.name:
        if len(before.channel.members) == 0:
            await before.channel.delete()

# --- コマンド部分 ---

# 1. コピー対象を設定するコマンド
@tree.command(name="set_copy", description="コピーする対象を指定します（空欄で自分）")
@app_commands.describe(target="コピーしたい相手（メンション）を選んでください")
async def set_copy(interaction: discord.Interaction, target: discord.Member = None):
    if target:
        user_copy_map[interaction.user.id] = target.id
        await interaction.response.send_message(
            f"✅ コピー対象を **{target.display_name}** さんに設定しました。\n"
            f"作成されるVCの名前と読み上げに反映されます。", 
            ephemeral=True
        )
    else:
        user_copy_map.pop(interaction.user.id, None)
        await interaction.response.send_message(
            "🔄 コピー設定をリセットしました（自分自身を使用します）。", 
            ephemeral=True
        )

# 2. グローバルボイスのカテゴリーと入り口VCを作成するコマンド
@tree.command(name="setup_global_vc", description="グローバルボイス用のカテゴリーと入り口を設置します")
async def setup_global_vc(interaction: discord.Interaction):
    guild = interaction.guild
    
    # 「グローバルボイス」カテゴリーを作成（既にある場合はそれを使う）
    category = discord.utils.get(guild.categories, name="グローバルボイス")
    if category is None:
        category = await guild.create_category("グローバルボイス")
    
    # 入り口となるVCを作成
    entrance_vc = await guild.create_voice_channel(
        name="➕ ここに入ると作成",
        category=category
    )
    
    # サーバーごとの入り口IDを登録（on_voice_state_updateで使用）
    parent_vcs[guild.id] = entrance_vc.id
    
    # パネル（案内メッセージ）を送信
    embed = discord.Embed(
        title="🌐 グローバルボイスパネル",
        description=(
            f"設置が完了しました！\n\n"
            f"1. {entrance_vc.mention} に入ると、あなたの専用VCが作られます。\n"
            f"2. `/set_copy` で指定した人の名前と読み上げ設定が引き継がれます。\n"
            f"3. 誰もいなくなるとチャンネルは自動で削除されます。"
        ),
        color=discord.Color.blue()
    )
    
    await interaction.response.send_message(embed=embed)

# -----------------

@bot.event
async def on_member_update(before, after):
    # Bot自身（自分）の更新かチェック
    if after.id == bot.user.id:
        # 名前が「ちゃていちゃん」でない場合、強制的に変更する
        if after.display_name != "ちゃていちゃん":
            try:
                await after.edit(nick="ちゃていちゃん")
                print(f"名前を '{after.display_name}' から 'ちゃていちゃん' に戻しました。")
            except discord.Forbidden:
                # 権限がない（サーバー管理者の名前は変えられない、など）場合
                print("名前を変更する権限がありません。")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    # 起動時にすべてのサーバーで名前を確認・変更する
    for guild in bot.guilds:
        if guild.me.display_name != "ちゃていちゃん":
            try:
                await guild.me.edit(nick="ちゃていちゃん")
            except:
                pass

# --- 管理設定コマンド ---

# 送り先（ペースト先）のチャンネルIDを固定
DEST_CHANNEL_ID = 1495747010802876528 

@bot.command()
async def check_settings(ctx):
    """保存されている設定をチャットに表示する"""
    if os.path.exists(SETTING_FILE):
        with open(SETTING_FILE, "r") as f:
            data = f.read()
        await ctx.send(f"現在の設定ファイルの中身:\n```json\n{data}\n```")
    else:
        await ctx.send("設定ファイルがまだ作られていません。")

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

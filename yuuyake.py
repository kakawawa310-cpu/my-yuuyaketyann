import discord
from discord import app_commands
from discord.ext import commands
import random
import os
import re
import urllib.parse
from flask import Flask, request
from threading import Thread

# --- 1. 設定値とデータ保持 ---
current_log_channel_id = 1472220342889218250  # 初期ログチャンネルID
ID_LIST_CHANNEL_ID = 1472220342889218250      # 禁止IDが投稿されているチャンネルID
user_inventory = {}       # ユーザーの装備データ
channel_fun_modes = {}    # チャンネルごとのモード設定
battle_log_messages = {}  # 最新ログ上書き用メッセージの記録
BLACKLIST_GUILD_IDS = {}  # 禁止サーバーリスト
CHECK_JOIN_ENABLED = True
DELETE_INVITE_ENABLED = True
INVITE_REGEX = r"(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/([\w\-]+)"

# ガチャ・召喚のレアリティと強さ(weight)
GACHA_TABLE = [("💎 SSR: 伝説の聖剣", 50), ("✨ SR: 魔導の杖", 30), ("⚔️ R: 鋼鉄の剣", 15), ("🥢 N: 割り箸", 5)]
SUMMON_TABLE = [("🐉 SSR: バハムート", 55), ("🦅 SR: グリフォン", 35), ("🐺 R: ワーウルフ", 20), ("🐱 N: 迷い猫", 5)]

# --- 2. Webサーバー (Render維持用) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is alive!"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
def keep_alive(): Thread(target=run).start()

# --- 3. Botクラス定義 ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
    async def setup_hook(self): await self.tree.sync()

bot = MyBot()

# --- 4. 対戦システムクラス ---
class ChallengeView(discord.ui.View):
    def __init__(self, host, host_data):
        super().__init__(timeout=300)
        self.host = host
        self.host_data = host_data

    @discord.ui.button(label="この勝負に挑む！", style=discord.ButtonStyle.danger)
    async def challenge(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.host.id:
            return await interaction.response.send_message("自分には挑めません！", ephemeral=True)
        
        guest_data = user_inventory.get(interaction.user.id)
        if not guest_data:
            return await interaction.response.send_message("ガチャか召喚で装備を整えてください！", ephemeral=True)

        # 勝敗判定（重みに基づくランダム）
        total = self.host_data['weight'] + guest_data['weight']
        winner = self.host if random.randint(1, total) <= self.host_data['weight'] else interaction.user
        
        result_msg = (
            f"⚔️ **コロシアム決着** ⚔️\n"
            f"🔵 {self.host.mention} ({self.host_data['name']})\n"
            f"   vs\n"
            f"🔴 {interaction.user.mention} ({guest_data['name']})\n\n"
            f"🏆 勝者: **{winner.mention}** ！"
        )
        
        # 1. 募集メッセージを結果に書き換える（二重ログ防止）
        await interaction.response.edit_message(content=result_msg, view=None)

        # 2. 最新ログ表示用メッセージを上書き更新
        log_display = battle_log_messages.get(interaction.channel.id)
        if log_display:
            try: await log_display.edit(content=f"📝 **最新の戦闘記録**\n{result_msg}")
            except: pass

class BattleRecruitView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="対戦相手を募集", style=discord.ButtonStyle.primary, custom_id="recruit_final")
    async def recruit(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = user_inventory.get(interaction.user.id)
        if not data: return await interaction.response.send_message("装備がありません！", ephemeral=True)
        
        log_ch = bot.get_channel(current_log_channel_id)
        if not log_ch: return await interaction.response.send_message("ログチャンネル未設定です。", ephemeral=True)

        view = ChallengeView(interaction.user, data)
        # ログチャンネルに募集を飛ばす
        await log_ch.send(f"📢 **対戦者募集中！**\n挑戦者: {interaction.user.mention}\n装備: {data['name']}", view=view)
        await interaction.response.send_message(f"{log_ch.mention} で募集を開始しました！", ephemeral=True)

# --- 5. イベント処理 ---
async def update_blacklist():
    channel = bot.get_channel(ID_LIST_CHANNEL_ID)
    if channel:
        BLACKLIST_GUILD_IDS.clear()
        messages = [m async for m in channel.history(limit=200)]
        for i, m in enumerate(messages):
            if m.content.isdigit():
                guild_id = int(m.content)
                guild_name = messages[i+1].content if i+1 < len(messages) else "不明なサーバー"
                BLACKLIST_GUILD_IDS[guild_id] = guild_name

@bot.event
async def on_ready():
    print(f"✅ {bot.user} 起動完了")
    await update_blacklist()

@bot.event
async def on_member_join(member):
    if not CHECK_JOIN_ENABLED: return
    for banned_id, banned_name in BLACKLIST_GUILD_IDS.items():
        banned_guild = bot.get_guild(banned_id)
        if banned_guild and banned_guild.get_member(member.id):
            log_ch = bot.get_channel(current_log_channel_id)
            if log_ch: await log_ch.send(f"⚠️ **禁止鯖所属検知**: {member.mention} (鯖: {banned_name})")
            break

@bot.event
async def on_message(message):
    if message.author.bot: return
    
    # 招待リンク削除
    if DELETE_INVITE_ENABLED:
        match = re.search(INVITE_REGEX, message.content)
        if match:
            try:
                invite = await bot.fetch_invite(match.group(3))
                if invite.guild and invite.guild.id in BLACKLIST_GUILD_IDS:
                    await message.delete()
                    return await message.channel.send("⚠️ 禁止鯖への招待リンクを削除しました。", delete_after=5)
            except: pass

    # IDリスト更新
    if message.channel.id == ID_LIST_CHANNEL_ID and message.content.isdigit():
        await update_blacklist()
        return

    # お遊び反応
    mode = channel_fun_modes.get(message.channel.id)
    if mode:
        if (mode in ["all", "gacha"]) and message.content == "ガチャ":
            # 確率: SSR:1%, SR:5%, R:20%, N:74%
            item, weight = random.choices(GACHA_TABLE, weights=[1, 5, 20, 74])[0]
            user_inventory[message.author.id] = {"name": item, "weight": weight}
            await message.reply(f"🎰 結果: **{item}** を装備した！")
        elif (mode in ["all", "summon"]) and message.content == "召喚":
            # 確率: SSR:1%, SR:5%, R:20%, N:74%
            item, weight = random.choices(SUMMON_TABLE, weights=[1, 5, 20, 74])[0]
            user_inventory[message.author.id] = {"name": item, "weight": weight}
            await message.reply(f"🔮 召喚: **{item}** と契約した！")

# --- 6. スラッシュコマンド ---
@bot.tree.command(name="set_log_channel", description="ログ/募集メッセージの送信先を設定します")
async def set_log(interaction: discord.Interaction, channel: discord.TextChannel):
    global current_log_channel_id
    current_log_channel_id = channel.id
    await interaction.response.send_message(f"ログ先を {channel.mention} に設定しました。")

@bot.tree.command(name="fun_mode", description="ガチャ/召喚モードを設定（all, gacha, summon, off）")
@app_commands.choices(mode=[
    app_commands.Choice(name="両方", value="all"),
    app_commands.Choice(name="ガチャ", value="gacha"),
    app_commands.Choice(name="召喚", value="summon"),
    app_commands.Choice(name="オフ", value="off")
])
async def f_mode(interaction: discord.Interaction, mode: str):
    if mode == "off": channel_fun_modes.pop(interaction.channel.id, None)
    else: channel_fun_modes[interaction.channel.id] = mode
    await interaction.response.send_message(f"このチャンネルのモードを `{mode}` にしました。")

@bot.tree.command(name="setup_battle_field", description="対戦パネルと最新ログ更新欄を設置します")
async def setup_battle(interaction: discord.Interaction, log_channel: discord.TextChannel = None):
    await interaction.channel.send("⚔️ **コロシアム受付**\n対戦したい人は下のボタンで募集を開始！", view=BattleRecruitView())
    target_ch = log_channel or interaction.channel
    log_msg = await target_ch.send("📝 **最新の戦闘記録**\n(データなし)")
    battle_log_messages[interaction.channel.id] = log_msg
    await interaction.response.send_message(f"設置完了。ログ更新先: {target_ch.mention}", ephemeral=True)

@bot.tree.command(name="reset_name", description="Botの名前を変更します")
async def r_name(interaction: discord.Interaction, name: str):
    await bot.user.edit(username=name)
    await interaction.response.send_message(f"Botの名前を `{name}` に変更しました。")

# 起動
keep_alive()
bot.run(os.getenv("DISCORD_BOT_TOKEN"))

import discord
from discord import app_commands
from discord.ext import commands
import random
import os
from flask import Flask
from threading import Thread
import re

# --- 設定とデータ保持 ---
current_log_channel_id = None
channel_fun_modes = {}  # {channel_id: mode}
user_inventory = {}     # {user_id: {"name": str, "weight": int}}
battle_log_messages = {} # {original_msg_id: log_msg_id}
ID_LIST_CHANNEL_ID = 1472220342889218250 
BLACKLIST_GUILD_IDS = {} 
INVITE_REGEX = r"(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/([\w\-]+)"

# レアリティ設定 (名前, 重み/強さ)
GACHA_TABLE = [
    ("💎 SSR: 伝説の聖剣", 50), ("✨ SR: 魔導の杖", 30), ("⚔️ R: 鋼鉄の剣", 15), ("🥢 N: 割り箸", 5)
]
SUMMON_TABLE = [
    ("🐉 SSR: バハムート", 55), ("🦅 SR: グリフォン", 35), ("🐺 R: ワーウルフ", 20), ("🐱 N: 迷い猫", 5)
]

async def update_blacklist():
    """禁止リストをチャンネル履歴から更新"""
    channel = bot.get_channel(ID_LIST_CHANNEL_ID)
    if channel:
        BLACKLIST_GUILD_IDS.clear()
        messages = [m async for m in channel.history(limit=200)]
        for i, m in enumerate(messages):
            if m.content.isdigit():
                guild_id = int(m.content)
                guild_name = messages[i+1].content if i+1 < len(messages) else "不明なサーバー"
                BLACKLIST_GUILD_IDS[guild_id] = guild_name
                
app = Flask('')
@app.route('/')
def home(): return "Coliseum Bot is Live!"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
    async def setup_hook(self): await self.tree.sync()

bot = MyBot()

@bot.event
async def on_member_join(member):
    # 禁止リストにあるサーバーに本人が入っていないか確認
    for banned_id, banned_name in BLACKLIST_GUILD_IDS.items():
        banned_guild = bot.get_guild(banned_id)
        if banned_guild and banned_guild.get_member(member.id):
            log_ch = bot.get_channel(current_log_channel_id)
            if log_ch:
                await log_ch.send(f"⚠️ **禁止鯖所属者を検知**\nユーザー: {member.mention}\n該当鯖: {banned_name}\nID: `{banned_id}`")
            break
            
@bot.event
async def on_message(message):
    if message.author.bot: return

    # --- 追加: IDリストの自動更新 ---
    if message.channel.id == ID_LIST_CHANNEL_ID and message.content.isdigit():
        await update_blacklist()
        return

    # --- 追加: 招待リンクの自動削除 ---
    match = re.search(INVITE_REGEX, message.content)
    if match:
        invite_code = match.group(3)
        try:
            invite = await bot.fetch_invite(invite_code)
            if invite.guild and invite.guild.id in BLACKLIST_GUILD_IDS:
                await message.delete()
                await message.channel.send(f"⚠️ {message.author.mention} 禁止サーバーへの招待は削除されました。", delete_after=5)
                return 
        except: pass
            
@bot.event
async def on_ready():
    print(f"✅ {bot.user} 起動")
    await update_blacklist() # 起動時にリストを読み込む

    # --- (この下にガチャや召喚の処理を続ける) ---

# --- 対戦システム (ChallengeView) ---
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

        # レアリティの重み(weight)を使って勝率を計算
        total = self.host_data['weight'] + guest_data['weight']
        win_roll = random.randint(1, total)
        winner = self.host if win_roll <= self.host_data['weight'] else interaction.user
        
        result_msg = (
            f"⚔️ **コロシアム決着** ⚔️\n"
            f"🔵 {self.host.mention} ({self.host_data['name']})\n"
            f"   vs\n"
            f"🔴 {interaction.user.mention} ({guest_data['name']})\n\n"
            f"🏆 勝者: **{winner.mention}** ！"
        )
        
        await interaction.response.edit_message(content=result_msg, view=None)
        
        # 設定されたログチャンネルにも結果を送信
        if current_log_channel_id:
            log_ch = bot.get_channel(current_log_channel_id)
            if log_ch: await log_ch.send(f"📋 **公式記録**\n{result_msg}")

class BattleRecruitView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="対戦相手を募集", style=discord.ButtonStyle.primary, custom_id="recruit")
    async def recruit(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = user_inventory.get(interaction.user.id)
        if not data: return await interaction.response.send_message("装備がありません！", ephemeral=True)
        
        if not current_log_channel_id:
            return await interaction.response.send_message("ログチャンネルが設定されていません。", ephemeral=True)

        log_ch = bot.get_channel(current_log_channel_id)
        view = ChallengeView(interaction.user, data)
        await log_ch.send(f"📢 **対戦者募集中！**\n挑戦者: {interaction.user.mention}\n装備: {data['name']}\n下のボタンで参加！", view=view)
        await interaction.response.send_message(f"{log_ch.mention} で募集を開始しました！", ephemeral=True)

# --- イベント ---
@bot.event
async def on_message(message):
    if message.author.bot: return
    mode = channel_fun_modes.get(message.channel.id)
    if not mode: return

    import random
    if (mode in ["all", "gacha"]) and message.content == "ガチャ":
        item, weight = random.choices([ (i[0], i[1]) for i in GACHA_TABLE ], weights=[1, 5, 20, 74])[0]
        user_inventory[message.author.id] = {"name": item, "weight": weight}
        await message.reply(f"🎰 結果: **{item}** を装備した！")

    elif (mode in ["all", "summon"]) and message.content == "召喚":
        item, weight = random.choices([ (i[0], i[1]) for i in SUMMON_TABLE ], weights=[1, 5, 20, 74])[0]
        user_inventory[message.author.id] = {"name": item, "weight": weight}
        await message.reply(f"🔮 召喚: **{item}** と契約した！")

# --- コマンド ---
@bot.tree.command(name="set_log_channel", description="ログチャンネルを設定")
async def set_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    global current_log_channel_id
    current_log_channel_id = channel.id
    await interaction.response.send_message(f"ログ先を {channel.mention} に設定しました。")

@bot.tree.command(name="fun_mode", description="お遊びモード設定")
@app_commands.choices(mode=[
    app_commands.Choice(name="両方", value="all"),
    app_commands.Choice(name="ガチャ", value="gacha"),
    app_commands.Choice(name="召喚", value="summon"),
    app_commands.Choice(name="オフ", value="off")
])
async def fun_mode(interaction: discord.Interaction, mode: str):
    if mode == "off": channel_fun_modes.pop(interaction.channel.id, None)
    else: channel_fun_modes[interaction.channel.id] = mode
    await interaction.response.send_message(f"モードを `{mode}` にしました。")

@bot.tree.command(name="setup_battle_field", description="対戦パネルを設置")
async def setup_battle(interaction: discord.Interaction):
    await interaction.channel.send("⚔️ **コロシアム受付**\n戦いたい奴はボタンを押せ！", view=BattleRecruitView())
    await interaction.response.send_message("設置完了。", ephemeral=True)

Thread(target=run).start()
bot.run(os.getenv("DISCORD_BOT_TOKEN"))

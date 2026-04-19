import discord
from discord import app_commands
from discord.ext import commands
import re
import os
import random
from flask import Flask
from threading import Thread

# --- 設定値 ---
ID_LIST_CHANNEL_ID = 1472220342889218250
current_log_channel_id = 1472220342889218250
fun_channel_id = None
channel_fun_modes = {} 
user_inventory = {}
battle_log_messages = {}

app = Flask('')
@app.route('/')
def home(): return "Bot is alive!"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
def keep_alive(): Thread(target=run).start()

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
    async def setup_hook(self): await self.tree.sync()

bot = MyBot()

# --- 状態管理 ---
CHECK_JOIN_ENABLED = True
DELETE_INVITE_ENABLED = True
BLACKLIST_GUILD_IDS = {}
INVITE_REGEX = r"(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/([\w\-]+)"

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
        print(f"✅ 禁止リスト更新: {len(BLACKLIST_GUILD_IDS)}件")

@bot.event
async def on_ready():
    print(f"✅ {bot.user} 起動")
    await update_blacklist()

@bot.event
async def on_member_join(member):
    if not CHECK_JOIN_ENABLED: return
    for banned_id, banned_name in BLACKLIST_GUILD_IDS.items():
        banned_guild = bot.get_guild(banned_id)
        if banned_guild and banned_guild.get_member(member.id):
            log_channel = bot.get_channel(current_log_channel_id)
            if log_channel:
                await log_channel.send(f"⚠️ **禁止鯖所属者検知**\nユーザー: {member.mention}\n該当鯖: {banned_name}\nID: `{banned_id}`")
            break

# --- ここを1つにまとめました ---
    # 1. お遊びチャンネル専用の反応
@bot.event
async def on_message(message):
    if message.author.bot: return

    # 1. お遊び機能（モード判定）
    # お遊びチャンネルでの反応
    mode = channel_fun_modes.get(message.channel.id)
    if mode:
        import random
        if (mode == "all" or mode == "gacha") and message.content == "ガチャ":
            res = random.choices(["💎 SSR: 伝説の剣", "✨ SR: 魔法の杖", "🪵 R: ただの棒"], weights=[5, 25, 70])[0]
            user_inventory[message.author.id] = res # データを保存
            await message.reply(f"ガチャの結果... **{res}** を手に入れた！（対戦パネルで使用可能）")

        elif (mode == "all" or mode == "summon") and message.content == "召喚":
            res = random.choices(["✨ 伝説の神獣", "🐉 ドラゴン", "🐱 ぬこ"], weights=[5, 25, 70])[0]
            user_inventory[message.author.id] = res # データを保存
            await message.channel.send(f"{message.author.mention} は **{res}** を召喚して契約した！")


    # 2. ID登録処理（既存）
    if message.channel.id == ID_LIST_CHANNEL_ID and message.content.isdigit():
        await update_blacklist()
        return

    # 3. 招待リンク削除機能（既存）
    if DELETE_INVITE_ENABLED:
        match = re.search(INVITE_REGEX, message.content)
        if match:
            invite_code = match.group(3)
            try:
                invite = await bot.fetch_invite(invite_code)
                if invite.guild and invite.guild.id in BLACKLIST_GUILD_IDS:
                    await message.delete()
                    await message.channel.send(f"⚠️ 招待リンクを削除しました。", delete_after=5)
            except: pass

# --- スラッシュコマンド ---

class BattleRecruitView(discord.ui.View):
    def __init__(self, host=None):
        super().__init__(timeout=None)
        self.host = host # 募集した人

    @discord.ui.button(label="対戦を募集する", style=discord.ButtonStyle.primary, custom_id="recruit_btn")
    async def recruit(self, interaction: discord.Interaction, button: discord.ui.Button):
        item = user_inventory.get(interaction.user.id)
        if not item:
            return await interaction.response.send_message("ガチャか召喚で武器やモンスターを手に入れてから来てください！", ephemeral=True)
        
        view = BattleRecruitView(host=interaction.user)
        # 募集ボタンを「対戦を挑む」に変える
        button.label = "この人に挑む！"
        button.style = discord.ButtonStyle.danger
        button.callback = self.start_battle
        await interaction.response.send_message(f"⚔️ {interaction.user.mention} が対戦相手を募集中！ (使用: {item})", view=self)

    async def start_battle(self, interaction: discord.Interaction):
        if interaction.user.id == self.host.id:
            return await interaction.response.send_message("自分自身には挑めません！", ephemeral=True)
        
        guest_item = user_inventory.get(interaction.user.id)
        if not guest_item:
            return await interaction.response.send_message("対戦するには先にガチャか召喚をしてきてください！", ephemeral=True)

        # 対戦開始
        import random

class ChallengeView(discord.ui.View):
    def __init__(self, host, host_item):
        super().__init__(timeout=300)
        self.host = host
        self.host_item = host_item

    @discord.ui.button(label="この人に挑む！", style=discord.ButtonStyle.danger)
    async def challenge(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.host.id:
            return await interaction.response.send_message("自分には挑めません！", ephemeral=True)
        
        guest_item = user_inventory.get(interaction.user.id)
        if not guest_item:
            return await interaction.response.send_message("アイテムを持っていません！", ephemeral=True)

        winner = random.choice([self.host, interaction.user])
        result_msg = (
            f"⚔️ **対戦終了** ⚔️\n"
            f"🔵 {self.host.mention} ({self.host_item})\n"
            f"   vs\n"
            f"🔴 {interaction.user.mention} ({guest_item})\n\n"
            f"🏆 勝者: **{winner.mention}** ！"
        )
        
import random

# --- 1. 挑む側のボタン専用View ---
class ChallengeView(discord.ui.View):
    def __init__(self, host, host_item):
        super().__init__(timeout=300)
        self.host = host
        self.host_item = host_item

    @discord.ui.button(label="この人に挑む！", style=discord.ButtonStyle.danger)
    async def challenge(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.host.id:
            return await interaction.response.send_message("自分には挑めません！", ephemeral=True)
        
        guest_item = user_inventory.get(interaction.user.id)
        if not guest_item:
            return await interaction.response.send_message("対戦するにはアイテムが必要です！", ephemeral=True)

        # 勝敗判定
        winner = random.choice([self.host, interaction.user])
        result_msg = (
            f"⚔️ **対戦終了** ⚔️\n"
            f"🔵 {self.host.mention} ({self.host_item})\n"
            f"   vs\n"
            f"🔴 {interaction.user.mention} ({guest_item})\n\n"
            f"🏆 勝者: **{winner.mention}** ！"
        )
        
        # [処理1] 募集メッセージを結果に書き換えてボタンを消す
        await interaction.response.edit_message(content=result_msg, view=None)

        # [処理2] 指定されたチャンネルの「最新ログ」を上書き更新する
        # パネルが置かれたチャンネルIDをキーにしてメッセージを探す
        log_display = battle_log_messages.get(interaction.channel.id)
        if log_display:
            try:
                await log_display.edit(content=f"📝 **最新の戦闘記録**\n{result_msg}")
            except:
                pass # メッセージ削除済み等のエラー回避

        # [処理3] 全体ログ（履歴用）にも送信
        log_channel = bot.get_channel(current_log_channel_id)
        if log_channel:
            await log_channel.send(f"📋 **バトルログ**\n場所: {interaction.channel.mention}\n{result_msg}")

# --- 2. 募集パネル用View ---
class BattleRecruitView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="対戦を募集する", style=discord.ButtonStyle.primary, custom_id="recruit_start_v2")
    async def recruit(self, interaction: discord.Interaction, button: discord.ui.Button):
        item = user_inventory.get(interaction.user.id)
        if not item:
            return await interaction.response.send_message("ガチャや召喚でアイテムを手に入れてください！", ephemeral=True)
        
        # 挑むボタンがついた新しいメッセージを送信
        view = ChallengeView(host=interaction.user, host_item=item)
        await interaction.response.send_message(f"⚔️ {interaction.user.mention} が募集中！ (使用: {item})", view=view)

# --- 3. パネル設置コマンド ---
@bot.tree.command(name="setup_battle_field", description="パネルと最新ログ更新場所を設置します")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(log_channel="最新の対戦結果を更新し続けるチャンネル")
async def setup_battle_field(interaction: discord.Interaction, log_channel: discord.TextChannel = None):
    # パネル本体を設置
    await interaction.channel.send(
        "🛡️ **コロシアム**\nここで対戦相手を募集しよう！", 
        view=BattleRecruitView()
    )
    
    # 最新ログ表示用メッセージを設置
    target_channel = log_channel or interaction.channel
    log_msg = await target_channel.send("📝 **最新の戦闘記録**\n(まだ対戦データはありません)")
    
    # 設置情報を保存（再起動すると消えるので注意）
    battle_log_messages[interaction.channel.id] = log_msg
    
    await interaction.response.send_message(
        f"設置完了！\n最新ログ更新先: {target_channel.mention}", 
        ephemeral=True
    )

keep_alive()
bot.run(os.getenv("DISCORD_BOT_TOKEN"))

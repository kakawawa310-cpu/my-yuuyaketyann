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

class BattleRecruitView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # 1. 募集をかけるボタン
    @discord.ui.button(label="対戦を募集する", style=discord.ButtonStyle.primary, custom_id="recruit_start")
    async def recruit(self, interaction: discord.Interaction, button: discord.ui.Button):
        item = user_inventory.get(interaction.user.id)
        if not item:
            return await interaction.response.send_message("先にガチャか召喚をしてアイテムを手に入れてください！", ephemeral=True)
        
        # 募集メッセージを出し、そこに「挑む」ボタンがついたViewを渡す
        view = ChallengeView(host=interaction.user, host_item=item)
        await interaction.response.send_message(f"⚔️ {interaction.user.mention} が対戦相手を募集中！ (使用: {item})", view=view)

# 2. 挑む側のボタン専用View（ここを分離することでエラーを防ぎます）
class ChallengeView(discord.ui.View):
    def __init__(self, host, host_item):
        super().__init__(timeout=300) # 5分間有効
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
        
        # メッセージを更新してボタンを消す
        await interaction.response.edit_message(content=result_msg, view=None)

        # ログ送信
        log_channel = bot.get_channel(current_log_channel_id)
        if log_channel:
            await log_channel.send(f"📋 **バトルログ**\n場所: {interaction.channel.mention}\n{result_msg}")


# パネル設置コマンド
@bot.tree.command(name="setup_battle_field", description="対戦募集パネルを設置します")
async def setup_battle_field(interaction: discord.Interaction):
    await interaction.channel.send("🛡️ **コロシアムへようこそ**\n武器やモンスターを持っているなら、ここで対戦相手を募集しよう！", view=BattleRecruitView())
    await interaction.response.send_message("対戦パネルを設置しました。", ephemeral=True)

@bot.tree.command(name="fun_mode", description="このチャンネルのお遊びモードを設定します")
@app_commands.describe(mode="モードを選択してください")
@app_commands.choices(mode=[
    app_commands.Choice(name="両方有効", value="all"),
    app_commands.Choice(name="ガチャのみ", value="gacha"),
    app_commands.Choice(name="召喚のみ", value="summon"),
    app_commands.Choice(name="無効（解除）", value="off")
])
@app_commands.checks.has_permissions(administrator=True)
async def fun_mode(interaction: discord.Interaction, mode: str):
    global channel_fun_modes
    if mode == "off":
        if interaction.channel.id in channel_fun_modes:
            del channel_fun_modes[interaction.channel.id]
        await interaction.response.send_message("このチャンネルのお遊び機能を**解除**しました。")
    else:
        channel_fun_modes[interaction.channel.id] = mode
        mode_name = {"all": "両方", "gacha": "ガチャのみ", "summon": "召喚のみ"}[mode]
        await interaction.response.send_message(f"このチャンネルを **{mode_name}** モードに設定しました！")

@bot.tree.command(name="toggle_join", description="参加時チェックのON/OFF")
@app_commands.checks.has_permissions(administrator=True)
async def toggle_join(interaction: discord.Interaction):
    global CHECK_JOIN_ENABLED
    CHECK_JOIN_ENABLED = not CHECK_JOIN_ENABLED
    await interaction.response.send_message(f"参加時チェックを **{'有効' if CHECK_JOIN_ENABLED else '無効'}** にしました。")

@bot.tree.command(name="toggle_invite", description="招待リンク削除のON/OFF")
@app_commands.checks.has_permissions(administrator=True)
async def toggle_invite(interaction: discord.Interaction):
    global DELETE_INVITE_ENABLED
    DELETE_INVITE_ENABLED = not DELETE_INVITE_ENABLED
    await interaction.response.send_message(f"招待リンク削除を **{'有効' if DELETE_INVITE_ENABLED else '無効'}** にしました。")

@bot.tree.command(name="reset_name", description="Botの名前を変更します")
@app_commands.checks.has_permissions(administrator=True)
async def reset_name(interaction: discord.Interaction, new_name: str):
    try:
        await bot.user.edit(username=new_name)
        await interaction.response.send_message(f"Botの名前を `{new_name}` に変更しました。")
    except Exception as e:
        await interaction.response.send_message(f"エラーが発生しました: {e}")

keep_alive()
bot.run(os.getenv("DISCORD_BOT_TOKEN"))

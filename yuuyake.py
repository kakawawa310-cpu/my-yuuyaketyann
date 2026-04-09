import discord
from discord import app_commands
from discord.ext import commands
import os, json, re, asyncio
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta, timezone
import asyncio

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
        self.loop.create_task(update_status_loop(self))
        await self.tree.sync()

bot = MyBot()

class MultiPollView(discord.ui.View):
    def __init__(self, options, anonymous, hide_results, allow_multiple, roles_dict=None):
        super().__init__(timeout=None)
        self.options = options
        self.anonymous = anonymous
        self.hide_results = hide_results
        self.allow_multiple = allow_multiple
        self.roles_dict = roles_dict or {} # {選択肢名: ロールID}
        self.votes = {opt: [] for opt in options} # {選択肢名: [ユーザーID, ...]}

    async def cast_vote(self, interaction: discord.Interaction, option: str):
        user_id = interaction.user.id
        role_id = self.roles_dict.get(option)
        
        # --- 1. 多重投票が禁止(False)の場合の処理 ---
        if not self.allow_multiple:
            # 既に同じものに投票済みなら「取り消し」
            if user_id in self.votes[option]:
                self.votes[option].remove(user_id)
                msg = f"「{option}」への投票を取り消しました。"
                # ロールも剥奪
                if role_id:
                    role = interaction.guild.get_role(role_id)
                    if role: await interaction.user.remove_roles(role)
            else:
                # 他の選択肢からユーザーを削除（上書き）
                for opt, users in self.votes.items():
                    if user_id in users:
                        users.remove(user_id)
                        # 前のロールを剥奪（必要なら）
                        prev_role_id = self.roles_dict.get(opt)
                        if prev_role_id:
                            prev_role = interaction.guild.get_role(prev_role_id)
                            if prev_role: await interaction.user.remove_roles(prev_role)
                
                self.votes[option].append(user_id)
                msg = f"「{option}」に投票（上書き）しました！"
                if role_id:
                    role = interaction.guild.get_role(role_id)
                    if role: await interaction.user.add_roles(role)

        # --- 2. 多重投票が許可(True)の場合の処理 ---
        else:
            if user_id in self.votes[option]:
                self.votes[option].remove(user_id)
                msg = f"「{option}」への投票を取り消しました。"
                if role_id:
                    role = interaction.guild.get_role(role_id)
                    if role: await interaction.user.remove_roles(role)
            else:
                self.votes[option].append(user_id)
                msg = f"「{option}」に投票しました！"
                if role_id:
                    role = interaction.guild.get_role(role_id)
                    if role: await interaction.user.add_roles(role)

        # レスポンス送信
        await interaction.response.send_message(msg, ephemeral=True)
        
        # 画面更新（非表示設定でない場合）
        if not self.hide_results:
            await interaction.message.edit(embed=self.make_embed())

# --- コマンド登録部分の引数追加 ---
@bot.tree.command(name="advanced_poll", description="多機能投票を作成")
@app_commands.describe(
    allow_multiple="複数選択を許可するか (True=複数OK, False=1つのみで上書き)"
)
async def advanced_poll(
    interaction: discord.Interaction, 
    question: str, 
    options: str, 
    anonymous: bool = True, 
    hide_results: bool = False,
    allow_multiple: bool = False, # 追加
    role_ids: str = None
):
    opt_list = [o.strip() for o in options.split(",")]
    
    # ロールIDの辞書作成
    r_ids = [int(r.strip()) for r in role_ids.split(",")] if role_ids else []
    roles_dict = {opt_list[i]: r_ids[i] for i in range(min(len(opt_list), len(r_ids)))}

    view = MultiPollView(opt_list, anonymous, hide_results, allow_multiple, roles_dict)
    
    # ボタン生成 (各ボタンにコールバックを設定)
    for opt in opt_list:
        button = discord.ui.Button(label=opt, style=discord.ButtonStyle.primary)
        # 選択肢を引数に渡すために lambda や partial を使わず直接関数を定義
        async def make_callback(o=opt):
            async def callback(inter):
                await view.cast_vote(inter, o)
            return callback
        
        button.callback = await make_callback()
        view.add_item(button)

    await interaction.response.send_message(f"**【投票】{question}**", embed=view.make_embed(), view=view)

JST = timezone(timedelta(hours=9)) # 日本時間

async def update_status_loop(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now(JST)
        hour = now.hour
        base_name = "ゆーやけBot" # ここは自由に変えてね
        
        if 5 <= hour < 11: # 朝
            nick, act = f"{base_name}（ねむねむ）", discord.Activity(type=discord.ActivityType.watching, name="ゆねっさむの歌声")
        elif 11 <= hour < 18: # 昼
            nick, act = f"{base_name}（お仕事中）", discord.Activity(type=discord.ActivityType.competing, name="大くじ大会")
        else: # 夜
            nick, act = f"{base_name}（残業）", discord.Activity(type=discord.ActivityType.watching, name="ゆねっさむの子守唄")

        await bot.change_presence(status=discord.Status.online, activity=act)
        for guild in bot.guilds:
            try: await guild.me.edit(nick=nick)
            except: continue
        await asyncio.sleep(600) # 10分おきにチェック

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

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

# --- 1. 投票用UIクラス (締め切り対応版) ---
class MultiPollView(discord.ui.View):
    def __init__(self, question, options, anonymous, hide_results, allow_multiple, roles_dict=None):
        super().__init__(timeout=None)
        self.question = question
        self.options = options
        self.anonymous = anonymous
        self.hide_results = hide_results
        self.allow_multiple = allow_multiple
        self.roles_dict = roles_dict or {}
        self.votes = {opt: [] for opt in options}

    async def cast_vote(self, interaction: discord.Interaction, option: str):
        user_id = interaction.user.id
        role_id = self.roles_dict.get(option)
        
        # 複数投票不可の場合の上書き・取り消し処理
        if not self.allow_multiple:
            if user_id in self.votes[option]:
                self.votes[option].remove(user_id)
                msg = f"「{option}」への投票を取り消しました。"
                if role_id: await interaction.user.remove_roles(interaction.guild.get_role(role_id))
            else:
                for opt, users in self.votes.items():
                    if user_id in users:
                        users.remove(user_id)
                        prev_role = self.roles_dict.get(opt)
                        if prev_role: await interaction.user.remove_roles(interaction.guild.get_role(prev_role))
                self.votes[option].append(user_id)
                msg = f"「{option}」に投票しました（他は取消）。"
                if role_id: await interaction.user.add_roles(interaction.guild.get_role(role_id))
        else:
            # 複数投票可の場合
            if user_id in self.votes[option]:
                self.votes[option].remove(user_id)
                msg = f"「{option}」への投票を取り消しました。"
                if role_id: await interaction.user.remove_roles(interaction.guild.get_role(role_id))
            else:
                self.votes[option].append(user_id)
                msg = f"「{option}」に投票しました！"
                if role_id: await interaction.user.add_roles(interaction.guild.get_role(role_id))

        await interaction.response.send_message(msg, ephemeral=True)
        if not self.hide_results:
            await interaction.message.edit(embed=self.make_embed())

    def make_embed(self, closed=False):
        status = "【投票終了】" if closed else "【投票中】"
        embed = discord.Embed(title=f"{status} {self.question}", color=discord.Color.blue())
        for opt, users in self.votes.items():
            count = len(users)
            val = f"{count} 票" if not self.hide_results or closed else "🔒 非表示"
            if not self.anonymous and (not self.hide_results or closed):
                names = [f"<@{uid}>" for uid in users]
                val += f"\n({', '.join(names)})" if names else ""
            embed.add_field(name=opt, value=val, inline=False)
        return embed

    async def end_poll(self, channel):
        # グラフ作成処理
        labels = list(self.votes.keys())
        sizes = [len(v) for v in self.votes.values()]
        
        plt.figure(figsize=(6, 4))
        plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
        plt.title(self.question)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        file = discord.File(buf, filename="result.png")
        
        # 既存メッセージの無効化と結果送信
        self.stop() # ボタンを押せなくする
        await channel.send(f"⏰ **{self.question}** の投票が締め切られました！", embed=self.make_embed(closed=True), file=file)

# --- 2. コマンド部分 ---
@bot.tree.command(name="advanced_poll", description="日時指定の締め切りが可能な多機能投票")
@app_commands.describe(
    deadline_date="日付 (例: 2024-05-01)",
    deadline_time="時間 (例: 20:00)",
    allow_multiple="複数選択を許可するか"
)
async def advanced_poll(
    interaction: discord.Interaction, 
    question: str, 
    options: str, 
    deadline_date: str, 
    deadline_time: str,
    anonymous: bool = True, 
    hide_results: bool = False,
    allow_multiple: bool = False,
    role_ids: str = None
):
    # 日時の解析
    try:
        dt_str = f"{deadline_date} {deadline_time}"
        deadline_dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        now = datetime.datetime.now()
        
        wait_seconds = (deadline_dt - now).total_seconds()
        if wait_seconds < 0:
            await interaction.response.send_message("過去の日時は指定できません。", ephemeral=True)
            return
    except ValueError:
        await interaction.response.send_message("日時の形式が正しくありません。(例: 2024-05-01 と 20:00)", ephemeral=True)
        return

    opt_list = [o.strip() for o in options.split(",")]
    r_ids = [int(r.strip()) for r in role_ids.split(",")] if role_ids else []
    roles_dict = {opt_list[i]: r_ids[i] for i in range(min(len(opt_list), len(r_ids)))}

    view = MultiPollView(question, opt_list, anonymous, hide_results, allow_multiple, roles_dict)
    
    for opt in opt_list:
        button = discord.ui.Button(label=opt, style=discord.ButtonStyle.primary)
        async def make_cb(o=opt):
            async def cb(it): await view.cast_vote(it, o)
            return cb
        button.callback = await make_cb()
        view.add_item(button)

    await interaction.response.send_message(
        f"⏳ 締め切り: {deadline_date} {deadline_time}\n**【投票】{question}**", 
        embed=view.make_embed(), 
        view=view
    )

    # 締め切りまで待機して自動終了
    await asyncio.sleep(wait_seconds)
    await view.end_poll(interaction.channel)
    
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

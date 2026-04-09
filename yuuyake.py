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

# --- 1. 投票用UIクラス (ボタンと集計) ---
class MultiPollView(discord.ui.View):
    def __init__(self, options, anonymous, hide_results, roles_list=None):
        super().__init__(timeout=None)
        self.options = options
        self.anonymous = anonymous
        self.hide_results = hide_results
        self.roles_list = roles_list or []
        self.votes = {opt: [] for opt in options} # 誰が投票したか保持

    async def cast_vote(self, interaction: discord.Interaction, option: str, role_id: Optional[int]):
        # 既にどこかに投票していたら削除（1人1票）
        for users in self.votes.values():
            if interaction.user.id in users:
                users.remove(interaction.user.id)
        
        self.votes[option].append(interaction.user.id)

        # ロール付与 (指定があれば)
        status_msg = f"「{option}」に投票しました！"
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role:
                await interaction.user.add_roles(role)
                status_msg += f"\n✅ ロール {role.name} を付与しました。"

        # 結果を隠す設定なら自分だけに通知
        await interaction.response.send_message(status_msg, ephemeral=True)

        # 結果を表示する設定ならEmbedを更新
        if not self.hide_results:
            await interaction.message.edit(embed=self.make_embed())

    def make_embed(self):
        embed = discord.Embed(title="📊 多機能投票", color=discord.Color.green())
        for opt, users in self.votes.items():
            count = len(users)
            display_val = "🔒 非表示" if self.hide_results else f"{count} 票"
            # 匿名じゃない場合は名前を出す
            if not self.anonymous and not self.hide_results:
                names = [f"<@{uid}>" for uid in users]
                display_val += f"\n({', '.join(names)})" if names else ""
            embed.add_field(name=opt, value=display_val, inline=False)
        return embed

# --- 2. スラッシュコマンド部分 ---
@bot.tree.command(name="advanced_poll", description="詳細設定が可能な投票を作成します")
@app_commands.describe(
    question="質問内容",
    options="選択肢（カンマ区切り 例: A,B,C）",
    anonymous="匿名にするか (True/False)",
    hide_results="途中経過を隠すか (True/False)",
    show_chart="終了時に円グラフを出すか (True/False)",
    role_ids="付与するロールID（カンマ区切り、選択肢と同数入力）"
)
async def advanced_poll(
    interaction: discord.Interaction, 
    question: str, 
    options: str, 
    anonymous: bool = True, 
    hide_results: bool = False,
    show_chart: bool = False,
    role_ids: str = None
):
    opt_list = [o.strip() for o in options.split(",")]
    role_list = [int(r.strip()) for r in role_ids.split(",")] if role_ids else []

    view = MultiPollView(opt_list, anonymous, hide_results, role_list)
    
    # ボタンを動的に追加
    for i, opt in enumerate(opt_list):
        role_id = role_list[i] if i < len(role_list) else None
        button = discord.ui.Button(label=opt, custom_id=f"poll_{opt}")
        
        # クロージャで引数を固定してコールバック設定
        async def callback(inter, o=opt, r=role_id):
            await view.cast_vote(inter, o, r)
            
        button.callback = callback
        view.add_item(button)

    # 終了ボタン（管理者のみ）
    if show_chart:
        end_button = discord.ui.Button(label="投票終了・グラフ表示", style=discord.ButtonStyle.danger)
        async def end_callback(inter):
            # グラフ作成
            labels = view.votes.keys()
            sizes = [len(v) for v in view.votes.values()]
            plt.figure(figsize=(6, 4))
            plt.pie(sizes, labels=labels, autopct='%1.1f%%')
            plt.title(question)
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            file = discord.File(buf, filename="chart.png")
            await inter.response.send_message("投票結果のグラフです！", file=file)
            view.stop()

        end_button.callback = end_callback
        view.add_item(end_button)

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

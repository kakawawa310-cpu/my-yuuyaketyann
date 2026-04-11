import discord
from discord import app_commands
from discord.ext import commands
import os, json, re, asyncio
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta, timezone
import asyncio
import aiohttp
from aiohttp import web

# --- このかたまりを、関数の外（ファイルの上の方など）に置く ---
async def start_webapp():
    server = web.Application()
    server.add_routes([web.get('/callback', handle_callback)])
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080) 
    await site.start()

# --- 設定項目（Developer Portalからコピー） ---
CLIENT_ID = '1489974962730307707'
CLIENT_SECRET = 'XngYW24KhKsjeIxTYAFrPhq7FjgJdUVA'
REDIRECT_URI = 'https://onrender.com'
TARGET_GUILDS = 1176515964561526914,1490973087376740505

async def handle_callback(request):
    code = request.query.get('code')
    if not code:
        return web.Response(text="認可コードが見つかりません。")

    async with aiohttp.ClientSession() as session:
        # 1. アクセストークンの取得
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        }
        async with session.post('https://discord.com', data=data) as resp:
            token_data = await resp.json()
            access_token = token_data.get('access_token')

        if not access_token:
            return web.Response(text="アクセストークンの取得に失敗しました。")

        # 2. ユーザー情報の取得
        headers = {'Authorization': f'Bearer {access_token}'}
        async with session.get('https://discord.com', headers=headers) as resp:
            user_data = await resp.json()
            user_id = user_data.get('id')

        # 3. 指定したサーバーにユーザーを強制参加させる
        bot_headers = {'Authorization': f'Bot {bot.http.token}'}
        results = []
        for guild_id in TARGET_GUILDS:
            put_url = f'https://discord.com{guild_id}/members/{user_id}'
            async with session.put(put_url, headers=bot_headers, json={'access_token': access_token}) as r:
                results.append(f"Server {guild_id}: {r.status}")

    return web.Response(text=f"認証完了！結果: {', '.join(results)}")

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

# --- 投票管理クラス ---
class MultiPollView(discord.ui.View):
    def __init__(self, question, options, anonymous, hide_results, allow_multiple, roles_dict=None):
        super().__init__(timeout=None) # タイムアウトをなしに設定
        self.question = question
        self.options = options
        self.anonymous = anonymous
        self.hide_results = hide_results
        self.allow_multiple = allow_multiple
        self.roles_dict = roles_dict or {}
        self.votes = {opt: [] for opt in options}
        self.is_closed = False

    def make_embed(self, closed=False):
        status = "【投票終了】" if closed else "【投票受付中】"
        color = discord.Color.red() if closed else discord.Color.blue()
        embed = discord.Embed(title=f"{status} {self.question}", color=color)
        
        for opt, users in self.votes.items():
            count = len(users)
            # 投票中かつ非表示設定なら隠す。終了後は必ず表示。
            val = f"{count} 票" if not self.hide_results or closed else "🔒 集計中..."
            
            # 匿名じゃない場合はユーザー名を表示
            if not self.anonymous and (not self.hide_results or closed):
                names = [f"<@{uid}>" for uid in users]
                val += f"\n({', '.join(names)})" if names else ""
            
            embed.add_field(name=opt, value=val, inline=False)
        return embed

    async def cast_vote(self, interaction: discord.Interaction, option: str):
        if self.is_closed: return
        user_id = interaction.user.id
        role_id = self.roles_dict.get(option)
        msg = ""

        # 既存の投票を確認
        already_voted = user_id in self.votes[option]

        if not self.allow_multiple: # 1人1票（上書きモード）
            if already_voted:
                self.votes[option].remove(user_id)
                msg = f"❌ 「{option}」への投票を取り消しました。"
                if role_id: await interaction.user.remove_roles(interaction.guild.get_role(role_id))
            else:
                # 他の選択肢から削除
                for opt, users in self.votes.items():
                    if user_id in users:
                        users.remove(user_id)
                        old_role = self.roles_dict.get(opt)
                        if old_role: await interaction.user.remove_roles(interaction.guild.get_role(old_role))
                
                self.votes[option].append(user_id)
                msg = f"✅ 「{option}」に投票しました（前の投票は上書きされました）。"
                if role_id: await interaction.user.add_roles(interaction.guild.get_role(role_id))
        else: # 複数投票可
            if already_voted:
                self.votes[option].remove(user_id)
                msg = f"❌ 「{option}」への投票を取り消しました。"
                if role_id: await interaction.user.remove_roles(interaction.guild.get_role(role_id))
            else:
                self.votes[option].append(user_id)
                msg = f"✅ 「{option}」に投票しました！"
                if role_id: await interaction.user.add_roles(interaction.guild.get_role(role_id))

        await interaction.response.send_message(msg, ephemeral=True)
        if not self.hide_results: # 結果表示設定ならメインメッセージを更新
            await interaction.message.edit(embed=self.make_embed())

    async def end_poll(self, channel):
        self.is_closed = True
        self.stop() # ボタン入力を停止
        
        # 円グラフ作成
        labels = list(self.votes.keys())
        sizes = [len(v) for v in self.votes.values()]
        
        # 票が0の場合はグラフが崩れるので対策
        if sum(sizes) == 0:
            file = None
        else:
            plt.figure(figsize=(6, 4))
            plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
            plt.title(self.question)
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            file = discord.File(buf, filename="result.png")

        await channel.send(f"⏰ **投票終了**\n「{self.question}」の集計が終わりました！", embed=self.make_embed(closed=True), file=file)

# --- スラッシュコマンドの実装 ---
@bot.tree.command(name="poll_pro", description="日時指定・ロール付与対応の高度な投票")
@app_commands.describe(
    question="質問したい内容",
    options="選択肢（カンマ区切り。例: りんご,ばなな,みかん）",
    deadline_date="終了日 (例: 2024-12-31)",
    deadline_time="終了時間 (例: 23:59)",
    anonymous="誰が投票したか隠すか",
    hide_results="投票中に途中経過を隠すか",
    allow_multiple="複数選択を許可するか",
    role_ids="付与するロールID（カンマ区切り、選択肢の数と合わせてください）"
)
async def poll_pro(
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
    # 日時の検証
    try:
        target_dt = datetime.datetime.strptime(f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M")
        wait_time = (target_dt - datetime.datetime.now()).total_seconds()
        if wait_time < 0:
            return await interaction.response.send_message("過去の日時は設定できません！", ephemeral=True)
    except:
        return await interaction.response.send_message("日時の書き方が違います（例: 2024-05-01 20:00）", ephemeral=True)

    opt_list = [o.strip() for o in options.split(",")]
    r_list = [int(r.strip()) for r in role_ids.split(",")] if role_ids else []
    r_dict = {opt_list[i]: r_list[i] for i in range(min(len(opt_list), len(r_list)))}

    view = MultiPollView(question, opt_list, anonymous, hide_results, allow_multiple, r_dict)

    # ボタンを動的にセットアップ
    for opt in opt_list:
        btn = discord.ui.Button(label=opt, style=discord.ButtonStyle.secondary)
        async def _callback_gen(o=opt): # クロージャで選択肢を保持
            async def _cb(it): await view.cast_vote(it, o)
            return _cb
        btn.callback = await _callback_gen()
        view.add_item(btn)

    await interaction.response.send_message(
        f"📅 終了予定: {deadline_date} {deadline_time}\n設定: {'匿名' if anonymous else '記名'}, {'複数可' if allow_multiple else '1人1票'}",
        embed=view.make_embed(),
        view=view
    )

    # 指定時間まで待機
    await asyncio.sleep(wait_time)
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

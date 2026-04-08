import discord
from discord import app_commands
from discord.ext import commands
import random
from flask import Flask
from threading import Thread
import os
import json # 保存に必要
import re   # 招待監視に必要

# --- 設定保存用の関数 ---
CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {
        "channel_id": None,
        "roles": {
            "大当たり": {"id": None, "weight": 5, "text": "🎉 超ラッキー！大当たりです！"},
            "中当たり": {"id": None, "weight": 15, "text": "✨ おめでとう！中当たりです！"},
            "小当たり": {"id": None, "weight": 30, "text": "👍 やったね！小当たりです！"},
            "はずれ":   {"id": None, "weight": 50, "text": "🍵 残念、はずれでした。"}
        }
    }

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

config_data = load_config()

# --- Render用：Webサーバー設定 ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    # RenderはPORT環境変数を自動で割り振ります
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# --- Discord Bot本体の設定 ---

intents = discord.Intents.default()
intents.message_content = True 
intents.members = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("スラッシュコマンド同期完了")

bot = MyBot()

@bot.tree.command(name="check_id", description="IDから情報を取得します")
@app_commands.describe(category="知りたい情報の種類を選んでください", target_id="調べたいIDを入力してください")
@app_commands.choices(category=[
    app_commands.Choice(name="サーバー (鯖)", value="guild"),
    app_commands.Choice(name="ユーザー", value="user"),
    app_commands.Choice(name="メッセージ", value="message"),
    app_commands.Choice(name="イベント", value="event"),
])
async def check_id(interaction: discord.Interaction, category: str, target_id: str):
    await interaction.response.defer(ephemeral=True) # 処理に時間がかかる場合があるので保留
    
    try:
        tid = int(target_id)
        
        if category == "guild":
            guild = bot.get_guild(tid) or await bot.fetch_guild(tid)
            if guild:
                await interaction.followup.send(f"🏰 **サーバー情報**\n名前: {guild.name}\n人数: {guild.member_count}\n作成日: {guild.created_at.strftime('%Y/%m/%d')}")
            else:
                await interaction.followup.send("❌ そのサーバーにBotがいないため、情報を取得できません。")

        elif category == "user":
            user = await bot.fetch_user(tid)
            await interaction.followup.send(f"👤 **ユーザー情報**\n名前: {user.name}#{user.discriminator}\nBotか: {'はい' if user.bot else 'いいえ'}\n作成日: {user.created_at.strftime('%Y/%m/%d')}")

        elif category == "message":
            # メッセージは「チャンネルID」がないと直接取得できないため、Botが入っている全鯖から検索を試みます
            found = False
            for guild in bot.guilds:
                for channel in guild.text_channels:
                    try:
                        msg = await channel.fetch_message(tid)
                        await interaction.followup.send(f"💬 **メッセージ内容** (場所: {guild.name} > #{channel.name})\n内容: {msg.content}\n投稿者: {msg.author.name}")
                        found = True
                        break
                    except: continue
                if found: break
            if not found:
                await interaction.followup.send("❌ メッセージが見つかりませんでした。（Botがアクセスできる範囲外です）")

        elif category == "event":
            # イベント（Scheduled Event）情報の取得
            found_event = None
            for guild in bot.guilds:
                event = guild.get_scheduled_event(tid)
                if event:
                    found_event = event
                    break
            
            if found_event:
                await interaction.followup.send(f"📅 **イベント情報**\n名前: {found_event.name}\n場所: {found_event.location or '不明'}\n開始: {found_event.start_time.strftime('%Y/%m/%d %H:%M')}")
            else:
                await interaction.followup.send("❌ 該当するイベントが見つかりませんでした。")

    except ValueError:
        await interaction.followup.send("⚠️ IDは数字で入力してください。")
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラーが発生しました: {e}")

@bot.event
async def on_ready():
    # 「ゆねっさむの歌声 を視聴中」に設定
    activity = discord.Activity(
        type=discord.ActivityType.watching, 
        name="ゆねっさむの歌声"
    )
    
    # ステータスをオンラインにして、アクティビティを適用
    await bot.change_presence(status=discord.Status.online, activity=activity)
    
    # ログに出力（お問い合わせ先のリマインド）
    print('ステータス設定完了！お問い合わせは、宣伝茶亭のさぴょにゃんへ！')

# 監視対象のサーバーIDリスト
WATCH_GUILDS = [
    123617928892551299, 1054832544845135934, 1166328579223716000, 1193327216642244778,
    1207583181822365727, 1248621150993387543, 1258719438438400010, 1265525518590021763,
    1281910154018820178, 1296867381070659736, 1310530336178044939, 1313417956473966662,
    1322457233656774687, 13276344391984743207, 1334428044454133801, 1348936278007222312,
    1363816583637762128, 1403496250715803790, 1415950374556270615, 1417875141169512498,
    1418360870878318752, 1419684110376505378, 1420924251824848988, 1426163084468289589,
    1430524783237529603, 1433015067086964617, 1433383422218473504, 1435513720980639756,
    1439262755705061529, 1441664701024174203, 1442097975429042308, 1442671585889615874,
    1445296133747507263, 1448140819533136035, 1448270967976755223, 1451907191513813014,
    1457230103468834995, 1458364042384244871, 1463880038930845777, 1463342167417421940,
    1464705180393013454, 1467327401305440380, 1467533706901192869, 1476104535683371202,
    1476615644999848128, 1481247878067388550
]

# 自分のサーバーID（招待を消したい大元のサーバー）
MY_GUILD_ID = 000000000000000000  # ここを自分のサーバーIDに変更

@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return

    # 監視対象サーバーでの発言かチェック
    if message.guild.id in WATCH_GUILDS:
        # メッセージから招待コードを抽出
        invites = re.findall(r'(?:discord\.gg/|discord\.com/invite/)([\w-]+)', message.content)
        
        for code in invites:
            try:
                invite = await bot.fetch_invite(code)
                # その招待が自分のサーバーのものなら削除
                if invite.guild and invite.guild.id == MY_GUILD_ID:
                    await invite.delete(reason="許可されていないサーバーでの貼り付けにより自動無効化")
                    print(f"✅ 自鯖招待を無効化しました: {code} (場所: {message.guild.name})")
            except discord.NotFound:
                pass # すでに無効なコード
            except Exception as e:
                print(f"招待削除エラー: {e}")

    # 以降に既存の処理（bot.process_commandsなど）を続けてください
    await bot.process_commands(message) 
    
# --- 実行部分 ---
if __name__ == "__main__":
    keep_alive()
    # Renderの環境変数「TOKEN」から読み込み
    token = os.environ.get("TOKEN")
    if token:
        bot.run(token)
    else:
        print("エラー: トークンが設定されていません。RenderのEnvironment設定を確認してください。")

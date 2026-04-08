import discord
from discord import app_commands
from discord.ext import commands
import random
from flask import Flask
from threading import Thread
import os
import json

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

async def run_kuji(channel, user, guild):
    if config_data["channel_id"] is None:
        return await channel.send("⚠️ チャンネルが設定されていません。`/set_channel` を実行してください。")
    if channel.id != config_data["channel_id"]:
        return 

    ranks = list(config_data["roles"].keys())
    weights = [info["weight"] for info in config_data["roles"].values()]
    
    # 抽選
    outcome = random.choices(ranks, weights=weights)[0]
    res = config_data["roles"][outcome]
    
    # 表示の修正：res['text'] を指定
    await channel.send(f"🎲 {user.mention}さんの結果...\n**{res['text']}**")

    # ロール付与
    if res["id"] is not None:
        role = guild.get_role(res["id"])
        if role:
            try:
                await user.add_roles(role)
                await channel.send(f"✨ `{role.name}` ロールを付与しました！")
            except discord.Forbidden:
                await channel.send("❌ エラー: Botのロール順位をサーバー設定で一番上に上げてください。")

@bot.event
async def on_message(message):
    if message.author.bot:
        return 
    if message.content == "茶亭くじ":
        await run_kuji(message.channel, message.author, message.guild)
    await bot.process_commands(message)

@bot.tree.command(name="set_channel", description="このチャンネルをくじ専用にします")
@app_commands.checks.has_permissions(administrator=True)
async def set_channel(interaction: discord.Interaction):
    config_data["channel_id"] = interaction.channel_id
    save_config(config_data) # 保存
    await interaction.response.send_message(f"✅ このチャンネルをくじ専用に設定しました！", ephemeral=True)

@bot.tree.command(name="set_role", description="当たりの種類ごとにロールを設定します")
@app_commands.choices(rank=[
    app_commands.Choice(name="大当たり", value="大当たり"),
    app_commands.Choice(name="中当たり", value="中当たり"),
    app_commands.Choice(name="小当たり", value="小当たり"),
])
@app_commands.checks.has_permissions(administrator=True)
async def set_role(interaction: discord.Interaction, rank: str, role: discord.Role):
    config_data["roles"][rank]["id"] = role.id
    save_config(config_data) # 保存
    await interaction.response.send_message(f"✅ {rank}の付与ロールを `{role.name}` に設定しました！", ephemeral=True)

# --- 実行部分 ---
if __name__ == "__main__":
    keep_alive()
    # Renderの環境変数「TOKEN」から読み込み
    token = os.environ.get("TOKEN")
    if token:
        bot.run(token)
    else:
        print("エラー: トークンが設定されていません。RenderのEnvironment設定を確認してください。")

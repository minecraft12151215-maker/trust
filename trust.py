import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import datetime
import requests
import pandas as pd

# 載入本地端的 .env 檔案 (上傳到 Railway 時這行會自動被忽略並讀取雲端變數)
load_dotenv()

# 從環境變數讀取 Token 與 Channel ID
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')

# 設定機器人權限
intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

# 設定台灣時間 (UTC+8) 晚上 8 點播報
tz = datetime.timezone(datetime.timedelta(hours=8))
report_time = datetime.time(hour=20, minute=0, tzinfo=tz)

@bot.event
async def on_ready():
    print(f'機器人已成功登入：{bot.user}')
    # 確保定時任務只啟動一次
    if not daily_report.is_running():
        daily_report.start()
        print("已啟動每晚 8 點的排程播報任務。")

@tasks.loop(time=report_time)
async def daily_report():
    # 檢查是否為交易日 (週一到週五)，週末不播報
    today = datetime.datetime.now(tz)
    if today.weekday() >= 5: 
        return

    if not CHANNEL_ID:
        print("錯誤：找不到 CHANNEL_ID 環境變數")
        return
        
    channel = bot.get_channel(int(CHANNEL_ID))
    if channel:
        try:
            report_message = fetch_foreign_investor_data() 
            await channel.send(f"📊 **今日外資買賣超盤後統整 ({today.strftime('%Y-%m-%d')})**\n\n{report_message}")
        except Exception as e:
            await channel.send(f"⚠️ 抓取資料時發生錯誤：{e}")

def fetch_foreign_investor_data():
    """
    這裡負責透過 requests 與 pandas 抓取並清理證交所與櫃買中心的資料。
    """
    # TODO: 替換成實際抓取 TWSE 與 TPEx API 的邏輯
    # 這裡先回傳測試用的格式
    summary = (
        "**📈 上市外資買超前三名**：\n"
        "1. 台積電 (2330)\n"
        "2. 鴻海 (2317)\n"
        "3. 聯發科 (2454)\n\n"
        "**📉 上櫃外資買超前三名**：\n"
        "1. 雙鴻 (3324)\n"
        "2. 群聯 (8299)\n"
        "3. 系統電 (5309)\n\n"
        "*(資料來源：台灣證券交易所 / 櫃買中心)*"
    )
    return summary

if __name__ == "__main__":
    if not TOKEN:
        print("請確認已設置 DISCORD_TOKEN 環境變數！")
    else:
        bot.run(TOKEN)

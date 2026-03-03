import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import datetime
import requests
import pandas as pd
import urllib3

# 隱藏並忽略所有的 SSL 憑證警告 (無敵模式)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 載入 .env 變數
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix='!', intents=intents)

# 設定台灣時間 (UTC+8) 晚上 8 點播報
tz = datetime.timezone(datetime.timedelta(hours=8))
report_time = datetime.time(hour=20, minute=0, tzinfo=tz)

@bot.event
async def on_ready():
    print(f'機器人已成功登入：{bot.user}')
    if not daily_report.is_running():
        daily_report.start()
        print("已啟動每晚 8 點的法人籌碼排程播報任務。")

# --- 【獨立指令區】 ---

@bot.command(name='外資', help='手動查詢最新外資買賣超前十名')
async def manual_foreign(ctx):
    await ctx.send("🔄 正在連接【官方交易所】抓取外資資料，請稍候...")
    try:
        msg = fetch_official_data(investor_type="foreign")
        await ctx.send(msg)
    except Exception as e:
        await ctx.send(f"⚠️ 抓取資料時發生錯誤：{e}")

@bot.command(name='投信', help='手動查詢最新投信買賣超前十名')
async def manual_trust(ctx):
    await ctx.send("🔄 正在連接【官方交易所】抓取投信資料，請稍候...")
    try:
        msg = fetch_official_data(investor_type="trust")
        await ctx.send(msg)
    except Exception as e:
        await ctx.send(f"⚠️ 抓取資料時發生錯誤：{e}")

# ----------------------

@tasks.loop(time=report_time)
async def daily_report():
    today = datetime.datetime.now(tz)
    if today.weekday() >= 5: 
        return

    if not CHANNEL_ID:
        print("錯誤：找不到 CHANNEL_ID")
        return
        
    channel = bot.get_channel(int(CHANNEL_ID))
    if channel:
        await channel.send("🔄 定時任務：正在從官方交易所抓取今日法人資料...")
        try:
            foreign_msg = fetch_official_data(investor_type="foreign")
            await channel.send(foreign_msg)
            
            trust_msg = fetch_official_data(investor_type="trust")
            await channel.send(trust_msg)
        except Exception as e:
            await channel.send(f"⚠️ 抓取資料時發生錯誤：{e}")

def fetch_official_data(investor_type):
    today = datetime.datetime.now(tz)
    
    # 👉 【關鍵修正 1】：判斷時間。如果現在早於下午 3 點 (15:00)，代表當天資料還沒出，強迫往前推一天！
    if today.hour < 15:
        today -= datetime.timedelta(days=1)
    
    # 👉 【關鍵修正 2】：遇到六日，繼續往前推到禮拜五
    # 注意：如果今天是禮拜一早上，修正 1 會把它變成禮拜日，這裡修正 2 就會繼續把它推回禮拜五，完美銜接！
    if today.weekday() == 5: # 星期六
        today -= datetime.timedelta(days=1)
    elif today.weekday() == 6: # 星期日
        today -= datetime.timedelta(days=2)

    # 官方 API 需要的日期格式
    twse_date = today.strftime("%Y%m%d")
    tpex_date = f"{today.year - 1911}/{today.strftime('%m/%d')}"
    
    investor_name = "外資" if investor_type == "foreign" else "投信"
    msg = f"📊 **【{investor_name}買賣超前十檔統整】**\n*(資料來源：台灣證券交易所 / 櫃買中心)*\n📅 **資料日期：{today.strftime('%Y-%m-%d')}**\n\n"
    
    # --- 1. 抓取上市 (TWSE) ---
    try:
        twse_url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={twse_date}&selectType=ALL&response=json"
        # 👉 將 timeout 從 10 秒拉長到 30 秒，避免證交所網站半夜連線太慢
        res = requests.get(twse_url, verify=False, timeout=30).json()
        
        if res.get('stat') == 'OK' and 'data' in res:
            df_twse = pd.DataFrame(res['data'], columns=res['fields'])
            
            if investor_type == 'foreign':
                net_cols = [c for c in df_twse.columns if '外' in c and '買賣超' in c]
                net_col = net_cols[0] if net_cols else '外陸資買賣超股數(不含外資自營商)'
            else:
                net_cols = [c for c in df_twse.columns if '投信' in c and '買賣超' in c]
                net_col = net_cols[0] if net_cols else '投信買賣超股數'
                
            df_twse = df_twse[['證券代號', '證券名稱', net_col]].copy()
            df_twse.columns = ['Code', 'Name', 'Net']
            
            df_twse['Net'] = pd.to_numeric(df_twse['Net'].astype(str).str.replace(',', ''), errors='coerce') / 1000
            df_twse = df_twse[df_twse['Code'].str.len() == 4]
            
            top_buy = df_twse.nlargest(10, 'Net')
            top_sell = df_twse.nsmallest(10, 'Net')
            
            msg += f"**📈 上市{investor_name}買超**\n"
            for i, row in enumerate(top_buy.itertuples(), 1):
                msg += f"{i}. {row.Name} ({row.Code}) ➔ {int(row.Net):,} 張\n"
                
            msg += f"\n**📉 上市{investor_name}賣超**\n"
            for i, row in enumerate(top_sell.itertuples(), 1):
                msg += f"{i}. {row.Name} ({row.Code}) ➔ {int(row.Net):,} 張\n"
        else:
            msg += "⚠️ 上市資料尚未更新。\n"
    except Exception as e:
        msg += f"⚠️ 上市資料抓取失敗 ({e})\n"

    msg += "\n-----------------------\n\n"
    
    # --- 2. 抓取上櫃 (TPEx) ---
    try:
        tpex_url = f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={tpex_date}"
        res = requests.get(tpex_url, verify=False, timeout=30).json()
        
        if res.get('aaData'):
            df_tpex = pd.DataFrame(res['aaData'])
            
            net_idx = 10 if investor_type == 'foreign' else 13
            
            df_tpex = df_tpex[[0, 1, net_idx]].copy()
            df_tpex.columns = ['Code', 'Name', 'Net']
            df_tpex['Net'] = pd.to_numeric(df_tpex['Net'].astype(str).str.replace(',', ''), errors='coerce') / 1000
            df_tpex = df_tpex[df_tpex['Code'].str.len() == 4]
            
            top_buy = df_tpex.nlargest(10, 'Net')
            top_sell = df_tpex.nsmallest(10, 'Net')
            
            msg += f"**📈 上櫃{investor_name}買超**\n"
            for i, row in enumerate(top_buy.itertuples(), 1):
                msg += f"{i}. {row.Name} ({row.Code}) ➔ {int(row.Net):,} 張\n"
                
            msg += f"\n**📉 上櫃{investor_name}賣超**\n"
            for i, row in enumerate(top_sell.itertuples(), 1):
                msg += f"{i}. {row.Name} ({row.Code}) ➔ {int(row.Net):,} 張\n"
        else:
            msg += "⚠️ 上櫃資料尚未更新。\n"
    except Exception as e:
        msg += f"⚠️ 上櫃資料抓取失敗 ({e})\n"

    return msg

if __name__ == "__main__":
    if not TOKEN:
        print("請確認已設置 DISCORD_TOKEN 環境變數！")
    else:
        bot.run(TOKEN)

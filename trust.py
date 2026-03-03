import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import datetime
import requests
from bs4 import BeautifulSoup
import urllib3

# 隱藏警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 載入 .env 變數
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix='!', intents=intents)

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
    await ctx.send("🔄 正在連接【Yahoo 股市】抓取外資資料，請稍候...")
    try:
        msg = fetch_yahoo_rank(investor_type="foreign")
        await ctx.send(msg)
    except Exception as e:
        await ctx.send(f"⚠️ 抓取資料時發生錯誤：{e}")

@bot.command(name='投信', help='手動查詢最新投信買賣超前十名')
async def manual_trust(ctx):
    await ctx.send("🔄 正在連接【Yahoo 股市】抓取投信資料，請稍候...")
    try:
        msg = fetch_yahoo_rank(investor_type="trust")
        await ctx.send(msg)
    except Exception as e:
        await ctx.send(f"⚠️ 抓取資料時發生錯誤：{e}")

# ----------------------

@tasks.loop(time=report_time)
async def daily_report():
    today = datetime.datetime.now(tz)
    # 週末不播報
    if today.weekday() >= 5: 
        return

    if not CHANNEL_ID:
        print("錯誤：找不到 CHANNEL_ID")
        return
        
    channel = bot.get_channel(int(CHANNEL_ID))
    if channel:
        await channel.send("🔄 定時任務：正在從 Yahoo 股市抓取今日法人資料...")
        try:
            foreign_msg = fetch_yahoo_rank(investor_type="foreign")
            await channel.send(foreign_msg)
            
            trust_msg = fetch_yahoo_rank(investor_type="trust")
            await channel.send(trust_msg)
        except Exception as e:
            await channel.send(f"⚠️ 抓取資料時發生錯誤：{e}")

def fetch_yahoo_rank(investor_type):
    investor_name = "外資" if investor_type == "foreign" else "投信"
    investor_url_part = "foreign-investor" if investor_type == "foreign" else "investment-trust"
    
    msg = f"📊 **【{investor_name}今日買賣超前十檔統整】**\n*(資料來源：Yahoo 股市)*\n\n"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
    }
    
    # 依序抓取：上市買超、上市賣超、上櫃買超、上櫃賣超
    for market, market_name in [('TAI', '上市'), ('TWO', '上櫃')]:
        for action, action_name in [('buy', '買超'), ('sell', '賣超')]:
            
            url = f"https://tw.stock.yahoo.com/rank/{investor_url_part}-{action}?exchange={market}&period=day"
            
            try:
                res = requests.get(url, headers=headers, verify=False, timeout=15)
                soup = BeautifulSoup(res.text, 'html.parser')
                
                results = []
                
                for a_tag in soup.find_all('a', href=lambda x: x and '/quote/' in x):
                    row = a_tag.find_parent('li')
                    if not row:
                        continue
                        
                    texts = [t for t in row.stripped_strings]
                    
                    if len(texts) >= 8 and texts[0].isdigit():
                        rank = texts[0]
                        name = texts[1]
                        
                        # 👉 修正 1：用 .TW 或 .TWO 識別股票代號，解決消失的問題
                        code = ""
                        for t in texts:
                            if '.TW' in t or '.TWO' in t:
                                code = t.split('.')[0] # 把後面的 .TW 切掉
                                break
                        
                        # 👉 修正 2：精準抓取「買賣超」欄位
                        # Yahoo 後面 5 個數字固定為：[買進, 賣出, 買賣超, 成交量, 持股]
                        data_values = []
                        for t in reversed(texts):
                            if any(char.isdigit() for char in t):
                                data_values.append(t)
                            if len(data_values) == 5:
                                break
                        
                        # 倒數第三個就是「買賣超」
                        vol = data_values[2] if len(data_values) >= 3 else "0"
                        
                        name_string = f"{name} ({code})" if code else name
                        item = f"{rank}. {name_string} ➔ {vol} 張"
                        
                        if item not in results and len(results) < 10:
                            results.append(item)
                            
                    if len(results) >= 10:
                        break
                        
                if not results:
                    msg += f"⚠️ 查無 {market_name}{action_name} 資料 (可能尚未更新)。\n\n"
                else:
                    icon = "📈" if action == "buy" else "📉"
                    msg += f"**{icon} {market_name}{investor_name}{action_name}**\n" + "\n".join(results) + "\n\n"
                    
            except Exception as e:
                msg += f"⚠️ {market_name}{action_name} 抓取發生錯誤 ({e})\n\n"
                
        msg += "-----------------------\n\n"
        
    return msg

if __name__ == "__main__":
    if not TOKEN:
        print("請確認已設置 DISCORD_TOKEN 環境變數！")
    else:
        bot.run(TOKEN)

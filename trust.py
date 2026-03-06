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
        print("已啟動每晚 8 點的投信籌碼排程播報任務。")

@bot.command(name='投信', help='手動查詢最新投信買賣超前十名')
async def manual_trust(ctx):
    await ctx.send("🔄 正在連接【Yahoo 股市】抓取投信資料，請稍候...")
    try:
        msg = fetch_yahoo_trust_rank()
        await ctx.send(msg)
    except Exception as e:
        await ctx.send(f"⚠️ 抓取資料時發生錯誤：{e}")

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
        await channel.send("🔄 定時任務：正在從 Yahoo 股市抓取今日【投信】資料...")
        try:
            trust_msg = fetch_yahoo_trust_rank()
            await channel.send(trust_msg)
        except Exception as e:
            await channel.send(f"⚠️ 抓取資料時發生錯誤：{e}")

def fetch_yahoo_trust_rank():
    investor_url_part = "investment-trust"
    msg = f"📊 **【投信今日買賣超前十檔統整】**\n*(資料來源：Yahoo 股市)*\n\n"
    
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
                processed_codes = set() # 用來記錄抓過的股票，防止重複
                
                for a_tag in soup.find_all('a', href=lambda x: x and '/quote/' in x):
                    row = a_tag.find_parent('li')
                    if not row:
                        continue
                        
                    texts = [t for t in row.stripped_strings]
                    
                    # 精準抓取股票代號
                    code = ""
                    name = ""
                    for i, t in enumerate(texts):
                        if '.TW' in t or '.TWO' in t:
                            code = t.split('.')[0]
                            name = texts[i - 1] if i > 0 else "未知"
                            break
                    
                    # 確認有代號且還沒被記錄過
                    if code and code not in processed_codes:
                        processed_codes.add(code) # 記下來，確保不會重複抓
                        
                        if len(texts) >= 6:
                            vol = texts[-4] # 倒數第 4 格是買賣超
                            
                            # 👉 放棄原本的 texts[0]，直接用長度自己排 1 到 10 名
                            rank = len(results) + 1 
                            
                            item = f"{rank}. {name} ({code}) ➔ {vol} 張"
                            results.append(item)
                            
                    if len(results) >= 10:
                        break
                        
                if not results:
                    msg += f"⚠️ 查無 {market_name}{action_name} 資料 (可能尚未更新)。\n\n"
                else:
                    icon = "📈" if action == "buy" else "📉"
                    msg += f"**{icon} {market_name}投信{action_name}**\n" + "\n".join(results) + "\n\n"
                    
            except Exception as e:
                msg += f"⚠️ {market_name}{action_name} 抓取發生錯誤 ({e})\n\n"
                
        msg += "-----------------------\n\n"
        
    return msg

if __name__ == "__main__":
    if not TOKEN:
        print("請確認已設置 DISCORD_TOKEN 環境變數！")
    else:
        bot.run(TOKEN)

import discord
from discord.ext import commands, tasks
import yfinance as yf
import datetime
import asyncio
import requests
import urllib3  # 新增：用來處理 HTTPS 警告
from bs4 import BeautifulSoup
import re
import logging
import os
from dotenv import load_dotenv

# 載入 .env 檔案
load_dotenv()

# 關閉 yfinance 煩人的警告訊息
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# 關閉 requests 略過 SSL 檢查時產生的警告訊息 (重要！)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= 設定區 =================
# 1. 透過環境變數安全讀取 Token
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    raise ValueError("❌ 找不到 DISCORD_TOKEN！請確認 .env 檔案或 Railway 環境變數是否已設定。")

# 2. 請貼上你要發送訊息的 Discord 頻道 ID
TARGET_CHANNEL_ID = 1478022744284332081

# 3. 自動播報時間設定 (台灣時間)
REPORT_TIME = "20:00"

# 建立台灣專屬時區 (UTC+8)
tw_tz = datetime.timezone(datetime.timedelta(hours=8))
# =========================================

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8'
}

# ================= Discord 完美對齊工具 =================
def to_full_width(text):
    """將半形英數字轉換為全形，確保在 Discord 中絕對對齊"""
    res = ""
    for c in text:
        if 33 <= ord(c) <= 126:
            res += chr(ord(c) + 65248)
        elif c == ' ':
            res += '　'
        else:
            res += c
    return res

def format_stock_name(name, length=6):
    """名稱轉全形並固定長度，不足補全形空白"""
    fw_name = to_full_width(name)[:length]
    return fw_name + '　' * (length - len(fw_name))
# =======================================================

def fetch_trust_data():
    """使用富邦證券(MoneyDJ)的投信買賣超抓取引擎"""
    ANSI_RED = "\u001b[0;31m"    
    ANSI_GREEN = "\u001b[0;32m"  
    ANSI_YELLOW = "\u001b[0;33m" 
    ANSI_WHITE = "\u001b[0;37m"  
    ANSI_RESET = "\u001b[0m"

    print("🔍 開始從富邦證券掃描投信買賣超排行榜...")
    url = "https://fubon-ebrokerdj.fbs.com.tw/Z/ZG/ZGK_DD.djhtm"
    
    top_buy = []
    top_sell = []
    
    try:
        # ✅ 關鍵修改：加入 verify=False 強制略過 SSL 憑證檢查
        res = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        res.encoding = 'big5' 
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 增強版網頁解析：不寫死欄位數量，動態尋找資料
        for tr in soup.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) >= 6: # 只要有基本的 6 欄就嘗試解析
                text1 = tds[0].text.strip()
                if text1.isdigit(): # 確認第一欄是排名數字
                    # --- 處理左半邊：投信買超 ---
                    if len(top_buy) < 12:
                        buy_name_full = tds[1].text.strip()
                        buy_vol = tds[2].text.strip().replace(',', '')
                        buy_match = re.match(r'^([A-Z0-9]+)(.*)$', buy_name_full)
                        if buy_match:
                            top_buy.append({
                                'ticker': buy_match.group(1),
                                'name': buy_match.group(2).strip(),
                                'net_vol': buy_vol
                            })
                            
                    # --- 處理右半邊：投信賣超 ---
                    # 動態尋找右半邊的「排名」欄位到底在 index 幾
                    right_rank_idx = -1
                    for i in range(3, len(tds) - 2):
                        if tds[i].text.strip().isdigit():
                            right_rank_idx = i
                            break
                            
                    if right_rank_idx != -1 and len(top_sell) < 12:
                        sell_name_full = tds[right_rank_idx + 1].text.strip() 
                        sell_vol = tds[right_rank_idx + 2].text.strip().replace(',', '').replace('-', '') 
                        sell_match = re.match(r'^([A-Z0-9]+)(.*)$', sell_name_full)
                        if sell_match:
                            top_sell.append({
                                'ticker': sell_match.group(1),
                                'name': sell_match.group(2).strip(),
                                'net_vol': sell_vol
                            })
    except Exception as e:
        print(f"❌ 富邦投信網頁爬取或解析失敗: {e}")

    print(f"✅ 成功抓取: 買超 {len(top_buy)} 檔, 賣超 {len(top_sell)} 檔")

    all_targets = {"🔥 投信作帳衝刺 (買超排行)": top_buy, "🧊 投信結帳逃命 (賣超排行)": top_sell}
    results = {}

    for title, target_list in all_targets.items():
        if not target_list:
            continue # 如果該清單沒東西就跳過
            
        block_content = "```ansi\n"
        for item in target_list:
            str_ticker = item['ticker'].ljust(6)
            str_name = format_stock_name(item['name'], 6)
            str_vol = f"{int(item['net_vol']):,}".rjust(9) + "張"
            
            # 預設值
            str_price = "   N/A  "
            str_pct = "  ---   "
            color = ANSI_WHITE

            try:
                ticker_tw = f"{item['ticker']}.TW"
                df = yf.Ticker(ticker_tw).history(period="2d")
                if df.empty:
                    ticker_two = f"{item['ticker']}.TWO"
                    df = yf.Ticker(ticker_two).history(period="2d")
                
                if len(df) >= 2:
                    close = float(df['Close'].iloc[-1])
                    prev_close = float(df['Close'].iloc[-2])
                    chg_pct = ((close - prev_close) / prev_close) * 100
                    
                    if chg_pct > 0: color = ANSI_RED
                    elif chg_pct < 0: color = ANSI_GREEN
                    
                    str_price = f"${close:.2f}".rjust(8)
                    str_pct = f"{chg_pct:+.2f}%".rjust(8)
                elif len(df) == 1:
                    close = float(df['Close'].iloc[-1])
                    str_price = f"${close:.2f}".rjust(8)
            except Exception as e:
                print(f"⚠️ 無法取得 {item['ticker']} 的股價資訊: {e}")
            
            block_content += f"{str_ticker} {str_name} {str_price}  {color}{str_pct}{ANSI_RESET} | {ANSI_YELLOW}{str_vol}{ANSI_RESET}\n"
            
        block_content += "```"
        results[title] = block_content

    data_date = datetime.datetime.now(tw_tz).strftime("%Y-%m-%d")
    return results, data_date

async def send_trust_report(channel):
    msg = await channel.send("🦁 **正在盤點投信主力部隊，抓取今日投信進出明細...**")
    
    try:
        results, data_date = await asyncio.to_thread(fetch_trust_data)
        
        embed = discord.Embed(
            title=f"🏛️ 台股投信主力買賣超雷達 | {data_date}",
            description="追蹤本土投信主力今日最真實的籌碼佈局，鎖定作帳與結帳動向！",
            color=0x27ae60 
        )

        has_data = False
        for title, content in results.items():
            if content.strip() != "```ansi\n```":
                embed.add_field(name=title, value=content, inline=False)
                has_data = True

        if not has_data:
            embed.add_field(name="⚠️ 狀態回報", value="今日尚未有投信買賣超資料，或網頁來源格式變更導致無法解析。", inline=False)

        embed.set_footer(text="數據來源：富邦證券/yfinance ｜ 紅色=上漲 ｜ 綠色=下跌")
        
        await msg.edit(content=None, embed=embed)
    except Exception as e:
        await msg.edit(content=f"❌ 系統發生嚴重錯誤：`{e}`")

@tasks.loop(minutes=1)
async def schedule_task():
    now = datetime.datetime.now(tw_tz).strftime("%H:%M")
    if now == REPORT_TIME and TARGET_CHANNEL_ID:
        ch = bot.get_channel(TARGET_CHANNEL_ID)
        if ch: 
            await send_trust_report(ch)
        await asyncio.sleep(61) 

@bot.command()
async def trust(ctx):
    await send_trust_report(ctx.channel)

@bot.event
async def on_ready():
    print(f'✅ 投信監控引擎 {bot.user} 已上線並準備就緒！')
    if not schedule_task.is_running():
        schedule_task.start()

bot.run(TOKEN)

import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import datetime
import requests
from bs4 import BeautifulSoup
import urllib3

# 隱藏並忽略所有的 SSL 憑證警告
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
    await ctx.send("🔄 正在為您抓取【外資】最新籌碼資料，請稍候...")
    try:
        # 外資的網頁代碼是 zgk
        msg = fetch_fubon_moneydj_data(page_id="zgk", investor_name="外資")
        await ctx.send(msg)
    except Exception as e:
        await ctx.send(f"⚠️ 抓取資料時發生錯誤：{e}")

@bot.command(name='投信', help='手動查詢最新投信買賣超前十名')
async def manual_trust(ctx):
    await ctx.send("🔄 正在為您抓取【投信】最新籌碼資料，請稍候...")
    try:
        # 投信的網頁代碼是 zgl
        msg = fetch_fubon_moneydj_data(page_id="zgl", investor_name="投信")
        await ctx.send(msg)
    except Exception as e:
        await ctx.send(f"⚠️ 抓取資料時發生錯誤：{e}")

# ----------------------

@tasks.loop(time=report_time)
async def daily_report():
    today = datetime.datetime.now(tz)
    # 週末不播報 (0=週一, 6=週日)
    if today.weekday() >= 5: 
        return

    if not CHANNEL_ID:
        print("錯誤：找不到 CHANNEL_ID")
        return
        
    channel = bot.get_channel(int(CHANNEL_ID))
    if channel:
        await channel.send("🔄 定時任務：正在抓取今日法人買賣超資料...")
        try:
            # 晚上八點定時推播時，先發外資，再發投信
            foreign_msg = fetch_fubon_moneydj_data(page_id="zgk", investor_name="外資")
            await channel.send(foreign_msg)
            
            trust_msg = fetch_fubon_moneydj_data(page_id="zgl", investor_name="投信")
            await channel.send(trust_msg)
        except Exception as e:
            await channel.send(f"⚠️ 抓取資料時發生錯誤：{e}")

def fetch_fubon_moneydj_data(page_id, investor_name):
    # 正確套用網頁代碼 (zgk=外資, zgl=投信)，並固定 C=1 (依張數排序)
    twse_url = f"https://fubon-ebrokerdj.fbs.com.tw/z/zg/{page_id}.djhtm?A=D&B=0&C=1"
    tpex_url = f"https://fubon-ebrokerdj.fbs.com.tw/z/zg/{page_id}.djhtm?A=D&B=1&C=1"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
    }
    
    msg = f"📊 **【{investor_name}今日買賣超前十檔統整】**\n*(資料來源：富邦/MoneyDJ)*\n\n"
    
    for market, url in [("上市", twse_url), ("上櫃", tpex_url)]:
        try:
            res = requests.get(url, headers=headers, verify=False, timeout=10)
            res.encoding = 'big5'
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 抓取網頁上的資料日期
            date_text = "今日"
            for div in soup.find_all('div'):
                if div.text and '資料日期' in div.text:
                    date_text = div.text.strip().replace('資料日期：', '')
                    break
            
            msg += f"📅 **{market}資料日期：{date_text}**\n"
            
            buy_list = []
            sell_list = []
            
            rows = soup.find_all('tr')
            for row in rows:
                cols = [td.text.strip() for td in row.find_all('td')]
                
                # 確保表格欄位足夠且第一欄是數字（名次）
                if len(cols) >= 8:
                    if cols[0].isdigit() and len(buy_list) < 10:
                        buy_list.append(f"{cols[0]}. {cols[1]} ➔ {cols[2]} 張")
                    
                    if cols[5].isdigit() and len(sell_list) < 10:
                        sell_list.append(f"{cols[5]}. {cols[6]} ➔ {cols[7]} 張")
                        
                # 抓滿十名就結束
                if len(buy_list) >= 10 and len(sell_list) >= 10:
                    break
                    
            if not buy_list:
                msg += f"⚠️ 抓不到{market}資料，可能網頁格式變更。\n\n"
                continue

            msg += f"**📈 {market}{investor_name}買超**\n" + "\n".join(buy_list) + "\n\n"
            msg += f"**📉 {market}{investor_name}賣超**\n" + "\n".join(sell_list) + "\n"
            msg += "\n-----------------------\n\n"
            
        except Exception as e:
            msg += f"⚠️ {market}資料抓取失敗 ({e})\n\n"
            
    return msg

if __name__ == "__main__":
    if not TOKEN:
        print("請確認已設置 DISCORD_TOKEN 環境變數！")
    else:
        bot.run(TOKEN)

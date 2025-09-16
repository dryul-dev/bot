# main.py
import discord
from discord.ext import commands
import asyncio
import os
from discord.ext import tasks
from datetime import datetime, timezone,timedelta,time
import json
from config import DISCORD_TOKEN

KST = timezone(timedelta(hours=9))
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
bot.active_battles = {}



def load_data():
    if not os.path.exists("player_data.json"): return {}
    with open("player_data.json", 'r', encoding='utf-8') as f: return json.load(f)

def save_data(data):
    with open("player_data.json", 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

# ▼▼▼ 이 함수 전체를 복사해서 붙여넣으세요 ▼▼▼
@tasks.loop(minutes=1)
async def daily_reset_task():
    # KST를 사용하려면 파일 상단에 KST = timezone(timedelta(hours=9))가 정의되어 있어야 합니다.
    now = datetime.now(KST)
    if now.hour == 0 and now.minute == 0:
        all_data = load_data()
        for player_id in all_data:
            player_data = all_data[player_id]
            player_data["challenge_type"] = None
            player_data["challenge_registered_today"] = False
        save_data(all_data)
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 일일 도전 상태 초기화 완료.")


@bot.event
async def on_ready():
    print(f'{bot.user.name} 봇이 성공적으로 로그인했습니다!')
    print('------')
    daily_reset_task.start()



async def main():
    async with bot:
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await bot.load_extension(f'cogs.{filename[:-3]}')
                    print(f'{filename} Cog가 로드되었습니다.')
                except Exception as e:
                    print(f'❗️ {filename} Cog 로드 중 오류 발생: {e}')
        await bot.start(DISCORD_TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
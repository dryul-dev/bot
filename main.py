# main.py

import discord
from discord.ext import commands, tasks
import asyncio
import os
import json
from datetime import datetime, time, timedelta, timezone
from config import DISCORD_TOKEN

# 봇 기본 설정
BOT_PREFIX = "!"
KST = timezone(timedelta(hours=9))
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

# Cog들이 공유할 데이터를 bot 객체에 저장
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)
bot.active_battles = {}

# 데이터 관리 함수 (일일 초기화 태스크용)
def load_data():
    if not os.path.exists("player_data.json"): return {}
    with open("player_data.json", 'r', encoding='utf-8') as f: return json.load(f)

def save_data(data):
    with open("player_data.json", 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

# 일일 초기화 태스크
@tasks.loop(minutes=1)
async def daily_reset_task():
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

# 메인 함수: Cogs를 로드하고 봇을 실행
async def main():
    async with bot:
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await bot.load_extension(f'cogs.{filename[:-3]}')
                    print(f'{filename} Cog가 로드되었습니다.')
                except Exception as e:
                    print(f'{filename} Cog 로드 중 오류 발생: {e}')
        await bot.start(DISCORD_TOKEN)

# 비동기 메인 함수 실행
if __name__ == '__main__':
    asyncio.run(main())
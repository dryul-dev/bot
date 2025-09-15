# main.py

import discord
from discord.ext import commands, tasks
import asyncio
import os
from datetime import datetime, time, timedelta, timezone
from config import DISCORD_TOKEN

# 봇 기본 설정
BOT_PREFIX = "!"
KST = timezone(timedelta(hours=9))
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

# 일일 초기화 태스크는 메인 파일에 두는 것이 좋습니다.

@tasks.loop(minutes=1)
async def daily_reset_task():
    now = datetime.now(KST)
    if now.hour == 0 and now.minute == 0:
        all_data = load_data()
        for player_id in all_data: all_data[player_id]["challenge_type"] = None; all_data[player_id]["challenge_registered_today"] = False
        save_data(all_data); print("일일 도전 상태 초기화 완료.")
    pass

@bot.event
async def on_ready():
    print(f'{bot.user.name} 봇이 성공적으로 로그인했습니다!')
    print('------')
    daily_reset_task.start()

# 메인 함수: Cogs를 로드하고 봇을 실행
async def main():
    # cogs 폴더 안의 모든 .py 파일을 찾아서 로드
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f'{filename} Cog가 로드되었습니다.')
            except Exception as e:
                print(f'{filename} Cog 로드 중 오류 발생: {e}')

    # 봇 실행
    await bot.start(DISCORD_TOKEN)

# 비동기 메인 함수 실행
if __name__ == '__main__':
    asyncio.run(main())
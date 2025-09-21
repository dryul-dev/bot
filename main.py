# main.py
import discord
from discord.ext import commands
import asyncio
import os
from discord.ext import tasks
from datetime import datetime, timezone,timedelta
import pytz
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

@tasks.loop(minutes=5) # 5분마다 모든 유저를 확인
async def daily_reset_task():
    all_data = load_data()
    
    # 변경사항이 있었는지 확인하는 플래그
    data_changed = False

    # 모든 등록된 유저를 한 명씩 확인
    for player_id, player_data in all_data.items():
        if not player_data.get("registered"):
            continue

        # 유저의 시간대 불러오기 (없으면 KST가 기본값)
        user_tz_str = player_data.get("timezone", "Asia/Seoul")
        try:
            user_tz = pytz.timezone(user_tz_str)
        except pytz.UnknownTimeZoneError:
            user_tz = KST # 잘못된 값이면 KST로
        
        # 유저의 현지 시간 기준 오늘 날짜
        today_local_str = datetime.now(user_tz).strftime('%Y-%m-%d')
        
        # 마지막 초기화 날짜를 불러옴
        last_reset = player_data.get("last_daily_reset_date")

        # 마지막 초기화 날짜가 오늘과 다르다면 초기화 실행
        if last_reset != today_local_str:
            player_data["challenge_registered_today"] = False
            player_data["challenge_type"] = None
            player_data["last_daily_reset_date"] = today_local_str # 오늘 날짜로 기록 업데이트
            
            # 목표 등록 횟수도 초기화
            if "daily_goal_info" in player_data:
                player_data["daily_goal_info"]["count"] = 0

            data_changed = True
            print(f"[{datetime.now(KST).strftime('%H:%M')}] 유저({player_data.get('name')})의 일일 정보 초기화 (시간대: {user_tz_str})")

    # 변경사항이 있었을 경우에만 파일 저장
    if data_changed:
        save_data(all_data)
        print("일일 정보 초기화 및 데이터 저장 완료.")

# on_ready 함수도 수정이 필요할 수 있습니다.
@bot.event
async def on_ready():
    print(f'{bot.user.name} 봇이 성공적으로 로그인했습니다!')
    print('------')
    # 봇이 켜질 때, 루프가 즉시 시작되도록 보장
    if not daily_reset_task.is_running():
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
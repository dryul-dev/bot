# main.py
import discord
from discord.ext import commands
import asyncio
import os
from config import DISCORD_TOKEN

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
bot.active_battles = {}

@bot.event
async def on_ready():
    print(f'{bot.user.name} 봇이 성공적으로 로그인했습니다!')
    print('------')

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
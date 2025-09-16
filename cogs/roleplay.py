# cogs/roleplay.py

import discord
from discord.ext import commands
import json
import os
import aiohttp # 비동기 HTTP 요청을 위한 라이브러리

# --- 데이터 관리 함수 ---
def load_json(filename):
    if not os.path.exists(filename): return {}
    with open(filename, 'r', encoding='utf-8') as f: return json.load(f)

def save_json(data, filename):
    with open(filename, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

# --- Roleplay Cog 클래스 ---
class RoleplayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession() # 웹훅 요청을 위한 세션 생성

    # Cog가 언로드될 때 세션을 닫아주는 것이 좋습니다.
    async def cog_unload(self):
        await self.session.close()

    @commands.command(name="프로필생성")
    @commands.is_owner() # 관리자용 명령어로 제한
    async def create_profile(self, ctx, name: str, avatar_url: str):
        """새로운 가상 프로필을 등록합니다. !프로필생성 <이름> <이미지URL>"""
        profiles = load_json("profiles.json")
        if name in profiles:
            return await ctx.send(f"이미 '{name}' 이름의 프로필이 존재합니다.")
        
        profiles[name] = {"avatar_url": avatar_url}
        save_json(profiles, "profiles.json")
        await ctx.send(f"✅ 프로필 '{name}'이(가) 성공적으로 생성되었습니다.")

    @commands.command(name="웹훅설정")
    @commands.is_owner()
    async def set_webhook(self, ctx, webhook_url: str):
        """현재 채널에서 사용할 웹훅 URL을 등록합니다."""
        webhooks = load_json("webhooks.json")
        webhooks[str(ctx.channel.id)] = webhook_url
        save_json(webhooks, "webhooks.json")
        await ctx.message.delete() # 보안을 위해 URL이 포함된 원본 메시지 삭제
        await ctx.send(f"✅ 현재 채널의 웹훅이 성공적으로 설정되었습니다.", delete_after=5)

# cogs/roleplay.py 의 RoleplayCog 클래스 내부

    @commands.command(name="rp", aliases=["인물"])
    async def roleplay(self, ctx, *, content: str):
        webhooks = load_json("webhooks.json")
        channel_id_str = str(ctx.channel.id)
        
        if channel_id_str not in webhooks:
            return await ctx.send("이 채널에는 웹훅이 설정되지 않았습니다.", delete_after=10)

        webhook_info = webhooks[channel_id_str]
        webhook_url = webhook_info["url"]
        
        try:
            name, message = [part.strip() for part in content.split(":", 1)]
        except ValueError:
            await ctx.message.delete()
            return await ctx.send("잘못된 형식입니다. `!rp <이름>: <할 말>` 형식으로 입력해주세요.", delete_after=10)

        # ▼▼▼ 여기가 추가된 부분입니다 ▼▼▼
        # 현재 채널에 허용된 프로필인지 확인
        if name not in webhook_info.get("allowed_profiles", []):
            await ctx.message.delete()
            return await ctx.send(f"**{name}** 프로필은 이 채널에서 사용할 수 없습니다.", delete_after=10)
        # ▲▲▲ 여기가 추가된 부분입니다 ▲▲▲

        profiles = load_json("profiles.json")
        profile = profiles.get(name)
        if not profile:
            await ctx.message.delete()
            return await ctx.send(f"'{name}' 프로필을 찾을 수 없습니다.", delete_after=10)

        # 4. 웹훅으로 메시지 전송
        payload = {
            "username": name,
            "avatar_url": profile["avatar_url"],
            "content": message
        }
        
        try:
            # 원본 명령어 메시지를 먼저 삭제
            await ctx.message.delete()
            # 웹훅 전송
            async with self.session.post(webhook_url, json=payload) as response:
                if response.status not in [200, 204]:
                    await ctx.send(f"웹훅 메시지 전송에 실패했습니다. (상태 코드: {response.status})", delete_after=10)
        except Exception as e:
            print(f"웹훅 전송 중 오류 발생: {e}")
            await ctx.send(f"오류가 발생하여 메시지를 보낼 수 없습니다.", delete_after=10)


async def setup(bot):
    await bot.add_cog(RoleplayCog(bot))
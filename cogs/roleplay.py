# cogs/roleplay.py (최종 수정 버전)

import discord
from discord.ext import commands
import json
import os
import aiohttp

# --- 데이터 관리 함수 ---
def load_profiles():
    if not os.path.exists("profiles.json"): return {}
    with open("profiles.json", 'r', encoding='utf-8') as f: return json.load(f)

def save_profiles(data):
    with open("profiles.json", 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

# --- Roleplay Cog 클래스 ---
class RoleplayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        await self.session.close()

    @commands.command(name="프로필생성")
    @commands.is_owner()
    async def create_profile(self, ctx, name: str, avatar_url: str, webhook_url: str):
        """새로운 가상 프로필을 등록합니다. !프로필생성 <이름> <이미지URL> <웹훅URL>"""
        webhook_url = webhook_url.strip('<>')
        profiles = load_profiles()
        if name in profiles:
            return await ctx.send(f"이미 '{name}' 이름의 프로필이 존재합니다.")
        
        # 웹훅 URL 유효성 간단 검사
        if not webhook_url.startswith("https://discord.com/api/webhooks/"):
            return await ctx.send("올바른 디스코드 웹훅 URL을 입력해주세요.")

        profiles[name] = {
            "avatar_url": avatar_url,
            "webhook_url": webhook_url
        }
        save_profiles(profiles)
        await ctx.send(f"✅ 프로필 '{name}'이(가) 성공적으로 생성되었습니다.")
        
    @commands.command(name="프로필삭제")
    @commands.is_owner()
    async def delete_profile(self, ctx, *, name: str):
        """기존 가상 프로필을 삭제합니다."""
        profiles = load_profiles()
        if name not in profiles:
            return await ctx.send(f"'{name}' 이름의 프로필을 찾을 수 없습니다.")
        
        del profiles[name]
        save_profiles(profiles)
        await ctx.send(f"🗑️ 프로필 '{name}'이(가) 삭제되었습니다.")

    @commands.command(name="rp", aliases=["인물"])
    async def roleplay(self, ctx, *, content: str):
        """가상 프로필로 메시지를 보냅니다. !rp <이름>: <할 말>"""
        try:
            name, message = [part.strip() for part in content.split(":", 1)]
        except ValueError:
            await ctx.message.delete(); return await ctx.send("잘못된 형식입니다. `!rp <이름>: <할 말>` 형식으로 입력해주세요.", delete_after=10)

        profiles = load_profiles()
        profile = profiles.get(name)
        if not profile:
            await ctx.message.delete(); return await ctx.send(f"'{name}' 프로필을 찾을 수 없습니다.", delete_after=10)

        webhook_url = profile["webhook_url"]
        payload = {
            "username": name,
            "avatar_url": profile["avatar_url"],
            "content": message
        }
        
        try:
            await ctx.message.delete()
            async with self.session.post(webhook_url, json=payload) as response:
                if response.status not in [200, 204]:
                    await ctx.send(f"웹훅 메시지 전송에 실패했습니다. (상태 코드: {response.status})", delete_after=10)
        except Exception as e:
            print(f"웹훅 전송 중 오류 발생: {e}")
            await ctx.send(f"오류가 발생하여 메시지를 보낼 수 없습니다.", delete_after=10)

async def setup(bot):
    await bot.add_cog(RoleplayCog(bot))
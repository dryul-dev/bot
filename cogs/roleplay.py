# cogs/roleplay.py (최종 수정 버전)

import discord
from discord.ext import commands
import json
import os
import aiohttp
import random

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
        if not (webhook_url.startswith("https://discord.com/api/webhooks/") or 
                webhook_url.startswith("https://discordapp.com/api/webhooks/")):
            return await ctx.send("올바른 디스코드 웹훅 URL을 입력해주세요.")
        profiles[name] = {
            "avatar_url": avatar_url,
            "webhook_url": webhook_url
        }
        save_profiles(profiles)
        await ctx.send(f"✅ 프로필 '{name}'이(가) 성공적으로 생성되었습니다.")


    # cogs/roleplay.py 의 RoleplayCog 클래스 내부에 추가

    @commands.command(name="프로필수정")
    @commands.is_owner()
    async def edit_profile(self, ctx, name: str, item_to_edit: str, *, new_value: str):
        """기존 프로필의 정보를 수정합니다. !프로필수정 <이름> <항목> <새 값>"""
        
        profiles = load_profiles()
        if name not in profiles:
            return await ctx.send(f"'{name}' 이름의 프로필을 찾을 수 없습니다.")

        item_to_edit = item_to_edit.lower()
        profile_data = profiles[name]

        if item_to_edit == "이름":
            if new_value in profiles:
                return await ctx.send(f"'{new_value}' 이름은 이미 다른 프로필이 사용하고 있습니다.")
            # 이름 변경 시, 기존 데이터를 새 이름으로 옮기고 이전 것은 삭제
            profiles[new_value] = profile_data
            del profiles[name]
            await ctx.send(f"✅ 프로필 이름이 '{name}'에서 '{new_value}'(으)로 변경되었습니다.")

        elif item_to_edit == "이미지":
            profile_data["avatar_url"] = new_value
            await ctx.send(f"✅ '{name}' 프로필의 이미지가 변경되었습니다.")

        elif item_to_edit == "웹훅":
            new_value = new_value.strip('<>')
            if not (new_value.startswith("https://discord.com/api/webhooks/") or 
                    new_value.startswith("https://discordapp.com/api/webhooks/")):
                return await ctx.send("올바른 디스코드 웹훅 URL을 입력해주세요.")
            
            profile_data["webhook_url"] = new_value
            await ctx.send(f"✅ '{name}' 프로필의 웹훅 URL이 변경되었습니다.")

        else:
            return await ctx.send("수정할 수 있는 항목은 `이름`, `이미지`, `웹훅` 입니다.")

        save_profiles(profiles)

    @edit_profile.error
    async def edit_profile_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("사용법: `!프로필수정 <기존이름> <수정항목> <새로운 값>`\n> 수정항목: `이름`, `이미지`, `웹훅`")
        elif isinstance(error, commands.NotOwner):
            await ctx.send("이 명령어는 봇 소유자만 사용할 수 있습니다.")
        
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


# cogs/roleplay.py 의 RoleplayCog 클래스 내부

    @commands.command(name="다이스")
    async def roll_dice(self, ctx, dice_string: str):
        """주사위를 굴립니다. (예: !다이스 2d6)"""
        try:
            rolls, sides = map(int, dice_string.lower().split('d'))
        except Exception:
            await ctx.send("잘못된 형식입니다. `[개수]d[면 수]` 형식으로 입력해주세요. (예: `2d6`)")
            return

        if not (1 <= rolls <= 100):
            return await ctx.send("주사위 개수는 1개에서 100개 사이로 입력해주세요.")
        if not (2 <= sides <= 1000):
            return await ctx.send("주사위 면 수는 2면에서 1000면 사이로 입력해주세요.")

        # 주사위를 굴려 총합만 계산
        total = sum(random.randint(1, sides) for _ in range(rolls))

        # 결과 메시지 생성
        embed = discord.Embed(
            title="🎲 주사위 굴림",
            description=f"**{ctx.author.display_name}**님이 **{rolls}d{sides}**를 굴려 **{total}**이(가) 나왔습니다.",
            color=discord.Color.dark_red()
        )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(RoleplayCog(bot))
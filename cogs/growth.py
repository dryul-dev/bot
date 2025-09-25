# cogs/growth.py

import discord
from discord.ext import commands
import json
import asyncio
import os
import random
from datetime import datetime, time, timedelta, timezone
import pytz


# Cog 외부의 헬퍼 함수 (데이터 로딩/저장)
def load_data():
    if not os.path.exists("player_data.json"): return {}
    with open("player_data.json", 'r', encoding='utf-8') as f: return json.load(f)

def save_data(data):
    with open("player_data.json", 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

# Cog 클래스 정의
class GrowthCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # KST, CLASSES 등 필요한 변수를 self에 저장할 수 있습니다.
        self.KST = timezone(timedelta(hours=9))
        self.CLASSES = ["마법사", "마검사", "검사"]

    # @bot.command 대신 @commands.command() 를 사용합니다.
    @commands.command(name="등록")
    async def register(self, ctx):
        player_id = str(ctx.author.id)
        all_data = load_data()
        if player_id in all_data and all_data[player_id].get("registered", False):
            await ctx.send("이미 등록된 플레이어입니다.")
            return

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            # 직업 선택
            await ctx.send(f"직업을 선택해주세요. (모든 문항 느낌표 없이 작성)\n> `{'`, `'.join(self.CLASSES)}`")
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            if msg.content not in self.CLASSES:
                await ctx.send("잘못된 직업입니다. 등록을 다시 시작해주세요.")
                return
            player_class = msg.content
            
            await ctx.send(f"**{player_class}**을(를) 선택하셨습니다. 확정하시겠습니까? (`예` 또는 `아니오`)")
            msg = await self.bot.wait_for('message', check=check, timeout=30.0)
            if msg.content.lower() != '예':
                await ctx.send("등록이 취소되었습니다.")
                return

            # 이름, 이모지, 색상 입력
            await ctx.send("사용할 이름을 입력해주세요.")
            name_msg = await self.bot.wait_for('message', check=check, timeout=60.0)

            forbidden_chars = ['*', '_', '~', '`', '|', '>']
            if any(char in name_msg.content for char in forbidden_chars):
                return await ctx.send(f"이름에는 특수문자를 사용할 수 없습니다.")
            
            await ctx.send("맵에서 자신을 나타낼 대표 이모지를 하나 입력해주세요.")
            emoji_msg = await self.bot.wait_for('message', check=check, timeout=60.0)

            await ctx.send("대표 색상을 HEX 코드로 입력해주세요. (예: `#FFFFFF`)")
            color_msg = await self.bot.wait_for('message', check=check, timeout=60.0)

            hex_code = color_msg.content
            if not (hex_code.startswith('#') and len(hex_code) == 7):
                return await ctx.send("잘못된 형식입니다. `#`을 포함한 7자리 HEX 코드를 입력해주세요.")
            try:
                int(hex_code[1:], 16)
            except ValueError:
                return await ctx.send("올바르지 않은 HEX 코드입니다. 0-9, A-F 사이의 문자를 사용해주세요.")

            all_data[player_id] = {
                "mental": 0, "physical": 0,
                "registered": True, "class": player_class, "name": name_msg.content, 
                "emoji": emoji_msg.content, "color": hex_code,
                "challenge_type": None, "challenge_registered_today": False,
                "rest_buff_active": False,
                "school_points": 0, "inventory": [],
                "goals": [], "daily_goal_info": {},
                "today_blessing": None,
                "last_blessing_date": None,
                "timezone": None,
                "attribute": None 
            }
            save_data(all_data)
            await ctx.send("🎉 등록이 완료되었습니다!")
        except asyncio.TimeoutError:
            await ctx.send("시간이 초과되어 등록이 취소되었습니다.")
            save_data(all_data)
            await ctx.send("🎉 등록이 완료되었습니다!")

        except asyncio.TimeoutError:
            await ctx.send("시간이 초과되어 등록이 취소되었습니다.")
        



    @commands.command(name="스탯조회")
    async def check_stats(self, ctx, member: discord.Member = None):
        """자신 또는 다른 플레이어의 프로필과 스탯 정보를 확인합니다."""
        target_user = member or ctx.author
        all_data = load_data()
        player_id = str(target_user.id)
        player_data = all_data.get(player_id)

        if not player_data or not player_data.get("registered", False):
            return await ctx.send(f"**{target_user.display_name}**님은 아직 `!등록`하지 않은 플레이어입니다.")
        
        # 스탯 계산
        mental = player_data.get('mental', 0)
        physical = player_data.get('physical', 0)
        total_stats = mental + physical
        level = 1 + total_stats // 5
        progress = total_stats % 5
        progress_bar = '■ ' * progress + '□ ' * (5 - progress)

    
        display_class = player_data.get("class")


        # Embed 생성
        embed = discord.Embed(
            title=f"{player_data.get('name', target_user.display_name)}님의 프로필",
            color=int(player_data.get('color', '#FFFFFF')[1:], 16)
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)
        
        # 프로필 정보 필드
        embed.add_field(name="직업", value=display_class, inline=True) # 수정된 display_class 변수 사용
        embed.add_field(name="레벨", value=f"**{level}**", inline=True)
        embed.add_field(name="대표 이모지", value=player_data.get('emoji', '❓'), inline=True)
        if player_data.get("attribute"):
            embed.add_field(name="속성", value=player_data.get("attribute"), inline=True)
        # 스탯 정보 필드
        embed.add_field(name="🧠 정신", value=f"`{mental}`", inline=True)
        embed.add_field(name="💪 육체", value=f"`{physical}`", inline=True)
        school_points = player_data.get('school_points', 0)
        embed.add_field(name="🎓 스쿨 포인트", value=f"`{school_points}`", inline=True)

        # 레벨업 진행도 필드
        embed.add_field(
            name=f"📊 다음 레벨까지 ({progress}/5)",
            value=f"**{progress_bar}**",
            inline=False
        )
        
        await ctx.send(embed=embed)
   
    @commands.command(name="정보수정")
    async def edit_info(self, ctx, item_to_edit: str, *, new_value: str):
        """자신의 이름, 이모지, 컬러 정보를 수정합니다."""
        all_data = load_data()
        player_id = str(ctx.author.id)
        player_data = all_data.get(player_id)

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")

        item_to_edit = item_to_edit.lower()
        editable_items = {"이름": "name", "이모지": "emoji", "컬러": "color"}

        if item_to_edit not in editable_items:
            return await ctx.send("수정할 수 있는 항목은 `이름`, `이모지`, `컬러` 입니다.")
        
        key_to_edit = editable_items[item_to_edit]

        # --- 입력값 유효성 검사 ---
        if key_to_edit == "name":
            forbidden_chars = ['*', '_', '~', '`', '|', '>']
            if any(char in new_value for char in forbidden_chars):
                return await ctx.send(f"이름에는 다음 특수문자를 사용할 수 없습니다: `{'`, `'.join(forbidden_chars)}`")
        
        elif key_to_edit == "color":
            if not (new_value.startswith('#') and len(new_value) == 7):
                return await ctx.send("잘못된 형식입니다. `#`을 포함한 7자리 HEX 코드를 입력해주세요.")
            try:
                int(new_value[1:], 16)
            except ValueError:
                return await ctx.send("올바르지 않은 HEX 코드입니다. 0-9, A-F 사이의 문자를 사용해주세요.")
        
        # --- 데이터 업데이트 및 저장 ---
        player_data[key_to_edit] = new_value
        save_data(all_data)
        
        await ctx.send(f"✅ **{item_to_edit}** 정보가 '{new_value}' (으)로 성공적으로 변경되었습니다.")
    @commands.command(name="리셋")
    async def reset_my_data(self, ctx):
        """자신의 모든 데이터(프로필, 스탯)를 완전히 초기화합니다."""
        
        player_id = str(ctx.author.id)
        all_data = load_data()

        if player_id not in all_data or not all_data[player_id].get("registered", False):
            await ctx.send("아직 등록된 정보가 없어 초기화할 수 없습니다.")
            return

        # 1단계: 사용자에게 재확인 받기 (경고 메시지 수정)
        embed = discord.Embed(
            title="⚠️ 모든 데이터 초기화 경고 ⚠️",
            description=f"**{ctx.author.display_name}**님, 정말로 모든 데이터를 초기화하시겠습니까?\n"
                        f"**직업, 이름, 스탯 등 모든 정보**가 영구적으로 사라지며 되돌릴 수 없습니다.\n\n"
                        f"동의하시면 30초 안에 `초기화 동의`라고 입력해주세요.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content == "초기화 동의"

        try:
            await self.bot.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            return await ctx.send("시간이 초과되어 초기화가 취소되었습니다.")

        # 2단계: 데이터 초기화 진행 (스탯 보존 로직 삭제)
        
        # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
        # 모든 정보를 담은 새로운 딕셔너리로 덮어씁니다.
        all_data[player_id] = {
            'mental': 0, # 스탯을 0으로 초기화
            'physical': 0, # 스탯을 0으로 초기화
            'registered': False,
            'class': None,
            'name': None,
            'emoji': None,
            'color': None,
            'attribute': None,
            'advanced_class': None,
            'challenge_type': None,
            'challenge_registered_today': False,
            'rest_buff_active': False,
            'today_blessing': None,
            'last_blessing_date': None,
            'timezone': None
            
        }
        # ▲▲▲ 여기가 수정된 부분입니다 ▲▲▲
        
        save_data(all_data)
        
        # 3단계: 완료 메시지 전송
        await ctx.send(f"✅ **{ctx.author.display_name}**님의 모든 데이터가 성공적으로 초기화되었습니다. `!등록` 명령어를 사용해 새로운 여정을 시작하세요!")
        """자신의 프로필 정보(직업, 이름 등)를 모두 초기화합니다. (스탯은 유지)"""


# cogs/growth.py 의 GrowthCog 클래스 내부에 추가

    @commands.command(name="속성부여")
    async def grant_attribute(self, ctx):
        """5레벨 도달 시 Gut, Wit, Heart 중 하나의 속성을 부여받습니다."""
        all_data = load_data()
        player_id = str(ctx.author.id)
        player_data = all_data.get(player_id)

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")
        
        if player_data.get("attribute") is not None:
            return await ctx.send(f"이미 `{player_data['attribute']}` 속성을 부여받았습니다.")

        level = 1 + ((player_data.get('mental', 0) + player_data.get('physical', 0)) // 5)
        if level < 5:
            return await ctx.send(f"속성 부여는 5레벨부터 가능합니다. (현재 레벨: {level})")

        attributes = ["Gut", "Wit", "Heart"]
        await ctx.send(f"부여받을 속성을 선택해주세요. (30초 안에 입력)\n> `{'`, `'.join(attributes)}`")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.title() in attributes

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=30.0)
            chosen_attribute = msg.content.title() # Gut, Wit, Heart 첫 글자 대문자로 통일

            player_data["attribute"] = chosen_attribute
            save_data(all_data)

            await ctx.send(f"✅ **{chosen_attribute}** 속성이 부여되었습니다! 이제 당신의 행동은 새로운 힘을 갖게 될 것입니다.")

        except asyncio.TimeoutError:
            await ctx.send("시간이 초과되어 속성 부여가 취소되었습니다.")


    @commands.command(name="시간대설정")
    async def set_timezone(self, ctx, timezone_name: str):
        """자신의 시간대를 설정합니다. (예: !시간대설정 Asia/Seoul)"""
        if timezone_name not in pytz.all_timezones:
            embed = discord.Embed(
                title="❌ 잘못된 시간대 이름입니다.",
                description="[이곳](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)에서 자신의 지역에 맞는 'TZ database name'을 찾아 정확하게 입력해주세요.",
                color=discord.Color.red()
            )
            embed.add_field(name="입력 예시", value="`!시간대설정 America/New_York`\n`!시간대설정 Europe/London`")
            return await ctx.send(embed=embed)

        all_data = load_data()
        player_id = str(ctx.author.id)
        player_data = all_data.get(player_id)
        if not player_data: return await ctx.send("먼저 `!등록`을 진행해주세요.")
            
        player_data['timezone'] = timezone_name
        save_data(all_data)
        
        user_tz = pytz.timezone(timezone_name)
        current_time = datetime.now(user_tz).strftime("%Y년 %m월 %d일 %H:%M")

        embed = discord.Embed(
            title="✅ 시간대 설정 완료",
            description=f"**{ctx.author.display_name}**님의 시간대가 **{timezone_name}**(으)로 설정되었습니다.",
            color=discord.Color.blue()
        )
        embed.add_field(name="현재 설정된 시간", value=current_time)
        await ctx.send(embed=embed)





    @commands.command(name="정신도전")
    async def register_mental_challenge(self, ctx):

        all_data = load_data()
        player_id = str(ctx.author.id)
        player_data = all_data.get(player_id, {}) # 데이터가 없는 유저를 위해 기본값 설정

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")

        user_tz_str = player_data.get("timezone", "Asia/Seoul")
        try:
            user_tz = pytz.timezone(user_tz_str)
        except pytz.UnknownTimeZoneError:
            user_tz = self.KST # 잘못된 값이 저장된 경우 KST로

        now_local = datetime.now(user_tz).time()

        if not (time(6, 0) <= now_local < time(14, 0)):
            embed = discord.Embed(title="❌ 도전 등록 실패", description=f"**도전 등록은 오전 6시부터 오후 2시까지만 가능합니다.**\n(현재 시간: {now_local.strftime('%H:%M')})", color=discord.Color.red())
            if "timezone" not in player_data:
                embed.set_footer(text="`!시간대설정` 명령어로 자신의 시간대를 설정할 수 있습니다.")
            await ctx.send(embed=embed)
            return

        all_data = load_data()
        player_id = str(ctx.author.id)
        if player_id not in all_data:
            all_data[player_id] = {"mental": 0, "physical": 0, "challenge_type": None, "challenge_registered_today": False}
        player_data = all_data[player_id]

        if player_data.get("challenge_registered_today", False):
            action_type = player_data.get("challenge_type", "알 수 없는 활동")
            # '완료됨' 상태에 대한 구체적인 메시지 추가
            if action_type == "완료됨":
                description = "이미 오늘의 도전을 성공적으로 완료했습니다. 내일 다시 시도해주세요."
            else:
                description = f"오늘은 이미 **'{action_type}'**을(를) 선택하셨습니다."
            
            embed = discord.Embed(
                title="⚠️ 이미 오늘의 활동을 마쳤습니다",
                description=description,
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return

        player_data["challenge_type"] = "정신도전"
        player_data["challenge_registered_today"] = True
        save_data(all_data)
        
        embed = discord.Embed(title="🧠 '정신' 도전 등록 완료!", description=f"**{ctx.author.display_name}**님, 오늘의 '정신' 도전이 정상적으로 등록되었습니다.", color=discord.Color.purple())
        embed.add_field(name="진행 안내", value="오후 4시 이후 `!도전완료` 명령어를 통해\n결과를 보고하고 스탯을 획득하세요!", inline=False)
        await ctx.send(embed=embed)
        pass

    @commands.command(name="육체도전")
    async def register_physical_challenge(self, ctx):

        all_data = load_data()
        player_id = str(ctx.author.id)
        player_data = all_data.get(player_id, {}) # 데이터가 없는 유저를 위해 기본값 설정

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")

        user_tz_str = player_data.get("timezone", "Asia/Seoul")
        try:
            user_tz = pytz.timezone(user_tz_str)
        except pytz.UnknownTimeZoneError:
            user_tz = self.KST # 잘못된 값이 저장된 경우 KST로

        now_local = datetime.now(user_tz).time()

        if not (time(6, 0) <= now_local < time(14, 0)):
            embed = discord.Embed(title="❌ 도전 등록 실패", description=f"**도전 등록은 오전 6시부터 오후 2시까지만 가능합니다.**\n(현재 시간: {now_local.strftime('%H:%M')})", color=discord.Color.red())
            if "timezone" not in player_data:
                embed.set_footer(text="`!시간대설정` 명령어로 자신의 시간대를 설정할 수 있습니다.")
            await ctx.send(embed=embed)
            return

        all_data = load_data()
        player_id = str(ctx.author.id)
        if player_id not in all_data:
            all_data[player_id] = {"mental": 0, "physical": 0, "challenge_type": None, "challenge_registered_today": False}
        player_data = all_data[player_id]

        if player_data.get("challenge_registered_today", False):
            action_type = player_data.get("challenge_type", "알 수 없는 활동")
            # '완료됨' 상태에 대한 구체적인 메시지 추가
            if action_type == "완료됨":
                description = "이미 오늘의 도전을 성공적으로 완료했습니다. 내일 다시 시도해주세요."
            else:
                description = f"오늘은 이미 **'{action_type}'**을(를) 선택하셨습니다."
            
            embed = discord.Embed(
                title="⚠️ 이미 오늘의 활동을 마쳤습니다",
                description=description,
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return

        player_data["challenge_type"] = "육체도전"
        player_data["challenge_registered_today"] = True
        save_data(all_data)
        
        embed = discord.Embed(title="💪 '육체' 도전 등록 완료!", description=f"**{ctx.author.display_name}**님, 오늘의 '육체' 도전이 정상적으로 등록되었습니다.", color=discord.Color.gold())
        embed.add_field(name="진행 안내", value="오후 4시 이후 `!도전완료` 명령어를 통해\n결과를 보고하고 스탯을 획득하세요!", inline=False)
        await ctx.send(embed=embed)


    @commands.command(name="도전완료")
    async def complete_challenge(self, ctx):

        all_data = load_data()
        player_id = str(ctx.author.id)
        player_data = all_data.get(player_id, {}) # 데이터가 없는 유저를 위해 기본값 설정

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")

        user_tz_str = player_data.get("timezone", "Asia/Seoul")
        try:
            user_tz = pytz.timezone(user_tz_str)
        except pytz.UnknownTimeZoneError:
            user_tz = self.KST
            
        # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
        # .time() 대신, 시간(hour)을 직접 비교하기 위해 datetime 객체 전체를 사용합니다.
        now_local = datetime.now(user_tz)
        
        # 현지 시간이 [오후 4시 이후] 이거나 [새벽 2시 이전]인 경우를 모두 허용합니다.
        if not (now_local.hour >= 16 or now_local.hour < 2): 
            embed = discord.Embed(title="❌ 도전 완료 실패", description=f"**도전 완료는 오후 4시부터 새벽 2시까지만 가능합니다.**\n(현재 시간: {now_local.strftime('%H:%M')})", color=discord.Color.red())
            if "timezone" not in player_data:
                embed.set_footer(text="`!시간대설정` 명령어로 자신의 시간대를 설정할 수 있습니다.")
            await ctx.send(embed=embed)
            return

            
        all_data = load_data()
        player_id = str(ctx.author.id)
        if player_id not in all_data:
            all_data[player_id] = {"mental": 0, "physical": 0, "challenge_type": None, "challenge_registered_today": False}
        player_data = all_data[player_id]
        
        challenge_type = player_data.get("challenge_type")

        if not player_data.get("challenge_registered_today", False) or challenge_type is None:
            embed = discord.Embed(title="🤔 완료할 도전이 없습니다", description="오늘 등록한 도전이 없거나, 이미 완료/휴식한 것 같습니다.", color=discord.Color.light_grey())
            await ctx.send(embed=embed)
            return
        
        if challenge_type == "휴식":
            embed = discord.Embed(title="🌙 오늘은 휴식을 선택했습니다", description="도전을 완료할 수 없습니다. 내일 다시 도전해주세요!", color=discord.Color.green())
            await ctx.send(embed=embed)
            return
            
        if challenge_type == "정신도전":
            player_data["mental"] += 1
            stat_name, emoji, color = "정신", "🧠", discord.Color.purple()
        elif challenge_type == "육체도전":
            player_data["physical"] += 1
            stat_name, emoji, color = "육체", "💪", discord.Color.gold()\
            
        
        
        # 완료 처리: challenge_type을 None으로 바꿔 중복 완료 방지
        player_data["challenge_type"] = "완료됨"
        save_data(all_data)
        
        embed = discord.Embed(title=f"{emoji} 도전 성공! {stat_name} 스탯 상승!", description=f"**{ctx.author.display_name}**님, 오늘의 도전을 성공적으로 완수했습니다.", color=color)
        embed.add_field(name="획득 스탯", value=f"**{stat_name} +1**", inline=False)
        await ctx.send(embed=embed)

        # `!스탯조회` 함수가 코드 내에 정의되어 있어야 합니다.
        await self.check_stats(ctx)


    @commands.command(name="휴식")
    async def take_rest(self, ctx):
        """6시~14시 사이에 오늘의 도전을 쉬고, 다음 전투를 위한 버프를 받습니다."""

        all_data = load_data()
        player_id = str(ctx.author.id)
        player_data = all_data.get(player_id, {}) # 데이터가 없는 유저를 위해 기본값 설정

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")

        user_tz_str = player_data.get("timezone", "Asia/Seoul")
        try:
            user_tz = pytz.timezone(user_tz_str)
        except pytz.UnknownTimeZoneError:
            user_tz = self.KST # 잘못된 값이 저장된 경우 KST로

        now_local = datetime.now(user_tz).time()

        if not (time(6, 0) <= now_local < time(14, 0)):
            embed = discord.Embed(title="❌ 휴식 선언 실패", description=f"**휴식 선언은 오전 6시부터 오후 2시까지만 가능합니다.**\n(현재 시간: {now_local.strftime('%H:%M')})", color=discord.Color.red())
            if "timezone" not in player_data:
                embed.set_footer(text="`!시간대설정` 명령어로 자신의 시간대를 설정할 수 있습니다.")
            await ctx.send(embed=embed)
            return

            
        all_data = load_data()
        player_id = str(ctx.author.id)
        if player_id not in all_data or not all_data[player_id].get("registered", False):
            await ctx.send("먼저 `!등록`을 진행해주세요.")
            return
        player_data = all_data[player_id]

        if player_data.get("challenge_registered_today", False):
            action_type = player_data.get("challenge_type", "활동")
            embed = discord.Embed(title="⚠️ 이미 오늘의 활동을 마쳤습니다", description=f"오늘은 이미 **'{action_type}'**을(를) 선택하셨습니다.", color=discord.Color.orange())
            await ctx.send(embed=embed)
            return

        player_data["challenge_type"] = "휴식"
        player_data["challenge_registered_today"] = True
        player_data["rest_buff_active"] = True
        save_data(all_data)

        embed = discord.Embed(title="🌙 편안한 휴식을 선택했습니다", description=f"**{ctx.author.display_name}**님, 오늘의 도전을 쉬고 재충전합니다.", color=discord.Color.green())
        embed.add_field(name="휴식 보너스", value="다음 전투 시작 시, 1회에 한해 **최대 체력이 증가**하는 효과를 받습니다.")
        await ctx.send(embed=embed)


    @commands.command(name="축복")
    async def blessing(self, ctx):
        """오늘의 축복 메시지를 확인합니다."""
        all_data = load_data()
        player_id = str(ctx.author.id)
        player_data = all_data.get(player_id)

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")

        # 축복 메시지 목록
        blessing_list = [
            "예상치 못한 곳에서 새로운 기회가 찾아올 것이니...",
            "흔들리지 않는 마음의 여유가 함께하리니...",
            "담대하라, 풀리지 않는 문제는 없으니...",
            "그대의 생각보다 강한 자임을 알라, 그대여...",
            "나아가라, 그대에게 불가능은 없으리니...",
            "쏟은 모든 사랑이 그대에게 돌아오리니...",
            "사랑 받기 마땅하고 존귀한 존재, 그대여...",
            "가장 좋은 일은 아직 일어나지 않았으니...",
            "어제보다 더 나은 오늘이 함께하리니...",
            "기억하라, 그대를 언제나 응원하고 있음을...",
            "있는 그대로의 그대가 가장 아름다우니...",
            "오늘의 수고가 내일을 바꾸리니, 그대여...",
            "넘어져도 괜찮다는 사실을 알라, 그대여...",
            "세상의 속도에 휩쓸리지 않으리니...",
            "마음 속에서 기쁨이 샘솟으리니..."
        ]

        user_tz_str = player_data.get("timezone", "Asia/Seoul")
        try:
            user_tz = pytz.timezone(user_tz_str)
        except pytz.UnknownTimeZoneError:
            user_tz = self.KST # 잘못된 값이 저장된 경우 KST로
        
        today_local_str = datetime.now(user_tz).strftime('%Y-%m-%d')
        last_blessing_date = player_data.get("last_blessing_date")

        # 2. 마지막으로 축복을 받은 날짜가 오늘(현지 기준)이 아니라면, 새로운 축복을 뽑습니다.
        if last_blessing_date != today_local_str:
            new_blessing = random.choice(blessing_list)
            player_data["today_blessing"] = new_blessing
            player_data["last_blessing_date"] = today_local_str # 오늘 날짜를 기록
            save_data(all_data)
            current_blessing = new_blessing
        # 3. 오늘 이미 축복을 받았다면, 저장된 축복을 불러옵니다.
        else:
            current_blessing = player_data.get("today_blessing", "오류: 오늘의 축복을 찾을 수 없습니다.")
        # --- ▲▲▲ 여기가 수정된 부분입니다 ▲▲▲ ---

        # Embed 생성 및 전송
        embed = discord.Embed(
            title="✨ 오늘의 축복 ✨",
            description=f"**{current_blessing}**",
            color=int(player_data['color'][1:], 16)
        )
        embed.set_footer(text=f"삼여신의 축복을 당신에게.")
        await ctx.send(embed=embed)

    
# cogs/growth.py 의 GrowthCog 클래스 내부

    @commands.command(name="목표등록")
    async def register_goal(self, ctx, *, goal_name: str):
        """오늘의 목표를 등록합니다. (하루에 2번, 최대 10개)"""
        all_data = load_data()
        player_id = str(ctx.author.id)
        player_data = all_data.get(player_id)

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")

        if len(goal_name) > 10:
            return await ctx.send("목표는 공백 포함 10자 이내로 설정해주세요.")

        goals = player_data.get("goals", [])
        if len(goals) >= 10:
            return await ctx.send("최대 10개의 목표만 저장할 수 있습니다. `!목표달성`으로 공간을 확보해주세요.")

        # --- ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼ ---
        # 1. 유저의 시간대를 불러와 오늘 날짜를 계산합니다.
        user_tz_str = player_data.get("timezone", "Asia/Seoul")
        try:
            user_tz = pytz.timezone(user_tz_str)
        except pytz.UnknownTimeZoneError:
            user_tz = self.KST
        today_local_str = datetime.now(user_tz).strftime('%Y-%m-%d')
        
        # 2. 유저의 일일 목표 정보를 불러옵니다.
        daily_info = player_data.get("daily_goal_info", {})
        last_date = daily_info.get("date")
        daily_count = daily_info.get("count", 0)

        # 3. 마지막 등록일이 오늘이 아니라면, 카운트를 0으로 초기화합니다.
        if last_date != today_local_str:
            daily_count = 0

        # 4. 초기화된 카운트를 기준으로 2개가 넘었는지 확인합니다.
        if daily_count >= 2:
            return await ctx.send(f"목표는 현지 시간 기준 하루에 두 번까지만 등록할 수 있습니다. ({today_local_str})")
        
        # 5. 모든 검사를 통과했으면 목표를 추가하고 정보를 저장합니다.
        goals.append(goal_name)
        player_data["goals"] = goals
        player_data["daily_goal_info"] = {"date": today_local_str, "count": daily_count + 1}
        
        save_data(all_data)
        # --- ▲▲▲ 여기가 수정된 부분입니다 ▲▲▲ ---

        await ctx.send(f"✅ 새로운 목표가 등록되었습니다: **{goal_name}** (오늘 {daily_count + 1}/2번째)")



    @commands.command(name="목표조회")
    async def view_goals(self, ctx):
        """자신이 등록한 목표 목록을 확인합니다."""
        all_data = load_data()
        player_data = all_data.get(str(ctx.author.id))

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")

        goals = player_data.get("goals", [])
        
        embed = discord.Embed(
            title=f"🎯 {ctx.author.display_name}의 목표 목록",
            color=int(player_data.get('color', '#FFFFFF')[1:], 16)
        )

        if not goals:
            goal_list_str = "아직 등록된 목표가 없습니다."
        else:
            # 모든 목표에 번호를 부여합니다.
            goal_list_str = "\n".join(f"**{i+1}.** {goal}" for i, goal in enumerate(goals))

        embed.description = goal_list_str
        embed.set_footer(text="`!목표달성 [번호]`로 완료할 수 있습니다.")
        await ctx.send(embed=embed)

    @commands.command(name="목표달성")
    async def achieve_goal(self, ctx, goal_number: int):
        """번호가 부여된 목표를 달성 처리합니다."""
        if not (1 <= goal_number <= 10):
            return await ctx.send("1번에서 10번까지의 목표만 달성할 수 있습니다.")

        all_data = load_data()
        player_id = str(ctx.author.id)
        player_data = all_data.get(player_id)

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")

        goals = player_data.get("goals", [])
        
        if len(goals) < goal_number:
            return await ctx.send(f"{goal_number}번 목표가 존재하지 않습니다.")

        goal_to_achieve = goals[goal_number - 1]

        await ctx.send(f"**'{goal_to_achieve}'** 목표를 달성한 것이 맞습니까? (30초 안에 `예` 또는 `아니오` 입력)")
        

        def check(m): 
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['예', '아니오']
        
        try:
            # 2. 사용자의 응답 메시지(msg)를 받아옵니다.
            msg = await self.bot.wait_for('message', check=check, timeout=30.0)

            # 3. 응답이 '아니오'일 경우, 취소 메시지를 보내고 함수를 종료합니다.
            if msg.content.lower() == '아니오':
                return await ctx.send("작업이 취소되었습니다.")
                
        except asyncio.TimeoutError:
            return await ctx.send("시간이 초과되어 목표 달성이 취소되었습니다.")




        achieved_goal = goals.pop(goal_number - 1)
        player_data["goals"] = goals
        

        player_data['school_points'] = player_data.get('school_points', 0) + 2
        
        reward_list = ["🎓 스쿨 포인트 +2"]
        stat_up_message = ""

        if random.random() < 0.10:
            stat_choice = random.choice(['mental', 'physical'])
            player_data[stat_choice] = player_data.get(stat_choice, 0) + 1
            stat_kor = "정신" if stat_choice == 'mental' else "육체"
            stat_up_message = f"✨ **놀라운 성과! {stat_kor} 스탯 +1**"
            reward_list.append(stat_up_message)

        save_data(all_data)

        # 2. Embed 생성 및 전송
        embed = discord.Embed(
            title="🎉 목표 달성!",
            description=f"**'{achieved_goal}'** 목표를 성공적으로 완수했습니다!",
            color=int(player_data.get('color', '#FFFFFF')[1:], 16)
        )
        embed.add_field(name="[ 획득 보상 ]", value="\n".join(reward_list))
        
        await ctx.send(embed=embed)
   

# cogs/growth.py 의 GrowthCog 클래스 내부에 추가

    @commands.command(name="목표수정")
    async def edit_goal(self, ctx, goal_number: int, *, new_goal_name: str):
        """번호에 해당하는 목표의 내용을 수정합니다."""
        all_data = load_data()
        player_id = str(ctx.author.id)
        player_data = all_data.get(player_id)

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")

        # 새 목표 이름 글자 수 제한 확인
        if len(new_goal_name) > 10:
            return await ctx.send("새로운 목표는 공백 포함 10자 이내로 설정해주세요.")

        goals = player_data.get("goals", [])
        
        # 유효한 번호인지 확인
        if not (1 <= goal_number <= len(goals)):
            return await ctx.send(f"잘못된 번호입니다. 1번부터 {len(goals)}번까지의 목표만 수정할 수 있습니다.")

        # 목표 수정
        original_goal = goals[goal_number - 1]
        goals[goal_number - 1] = new_goal_name
        
        save_data(all_data)

        embed = discord.Embed(
            title="🎯 목표 수정 완료",
            description=f"**{goal_number}번** 목표의 내용이 성공적으로 변경되었습니다.",
            color=int(player_data.get('color', '#FFFFFF')[1:], 16)
        )
        embed.add_field(name="변경 전", value=original_goal, inline=False)
        embed.add_field(name="변경 후", value=new_goal_name, inline=False)
        
        await ctx.send(embed=embed)



    @commands.command(name="목표중단")
    async def abandon_goal(self, ctx, goal_number: int):
        """등록된 목표를 중단하고, 격려 포인트를 받습니다."""
        if not (1 <= goal_number <= 10):
            return await ctx.send("1번에서 10번까지의 목표만 중단할 수 있습니다.")

        all_data = load_data()
        player_id = str(ctx.author.id)
        player_data = all_data.get(player_id)

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")

        goals = player_data.get("goals", [])
        
        if len(goals) < goal_number:
            return await ctx.send(f"{goal_number}번 목표가 존재하지 않습니다.")

        goal_to_abandon = goals[goal_number - 1]

        # 사용자에게 재확인
        await ctx.send(f"**'{goal_to_abandon}'** 목표를 정말로 중단하시겠습니까? (30초 안에 `예` 또는 `아니오` 입력)")
        
        # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
        # 1. check 함수가 '예', '아니오'를 모두 유효한 응답으로 인식하게 합니다.
        def check(m): 
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['예', '아니오']
        
        try:
            # 2. 사용자의 응답 메시지(msg)를 받아옵니다.
            msg = await self.bot.wait_for('message', check=check, timeout=30.0)

            # 3. 응답이 '아니오'일 경우, 취소 메시지를 보내고 함수를 종료합니다.
            if msg.content.lower() == '아니오':
                return await ctx.send("작업이 취소되었습니다.")
                
        except asyncio.TimeoutError:
            return await ctx.send("시간이 초과되어 목표 중단이 취소되었습니다.")
        # 목표 목록에서 제거
        abandoned_goal = goals.pop(goal_number - 1)
        player_data["goals"] = goals
        
        # 격려 보상: 스쿨 포인트 +1
        player_data['school_points'] = player_data.get('school_points', 0) + 1
        save_data(all_data)

        await ctx.send(f"😊 **'{abandoned_goal}'** 목표를 중단했습니다. 다음 도전을 응원합니다! (스쿨 포인트 +1)")



    @commands.command(name="수동초기화")
    @commands.is_owner() # 봇 소유자만 실행 가능하도록 제한
    async def manual_reset_challenges(self, ctx):
        """[관리자용] 모든 유저의 일일 도전 상태를 수동으로 초기화합니다."""
        await ctx.send("모든 유저의 일일 도전 상태 초기화를 시작합니다...")
        
        all_data = load_data()
        reset_count = 0
        for player_id, player_data in all_data.items():
            # 도전 상태 플래그가 True인 경우에만 초기화 진행
            if player_data.get("challenge_registered_today") is True:
                player_data["challenge_registered_today"] = False
                player_data["challenge_type"] = None
                reset_count += 1
        
        save_data(all_data)
        await ctx.send(f"✅ 완료! 총 {reset_count}명의 유저 도전 상태를 초기화했습니다.")

    @manual_reset_challenges.error
    async def manual_reset_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("이 명령어는 봇 소유자만 사용할 수 있습니다.")

    @commands.command(name="데이터조회")
    @commands.is_owner() # 봇 소유자만 실행 가능하도록 제한
    async def view_user_data(self, ctx, target_user: discord.Member):
        """[관리자용] 특정 유저의 raw data를 json 형식으로 확인합니다."""
        
        all_data = load_data()
        target_id = str(target_user.id)
        player_data = all_data.get(target_id)

        if not player_data:
            return await ctx.send(f"{target_user.display_name}님의 데이터를 찾을 수 없습니다.")

        # json 데이터를 보기 좋게 문자열로 변환
        # indent=4는 보기 좋게 4칸 들여쓰기를, ensure_ascii=False는 한글이 깨지지 않게 합니다.
        data_str = json.dumps(player_data, indent=4, ensure_ascii=False)
        
        # 데이터가 너무 길 경우를 대비하여 여러 메시지로 나누어 보낼 수 있도록 처리
        if len(data_str) > 1900:
            await ctx.send(f"📄 **{target_user.display_name}**님의 데이터가 너무 길어 여러 부분으로 나누어 표시합니다.")
            for i in range(0, len(data_str), 1900):
                chunk = data_str[i:i+1900]
                await ctx.send(f"```json\n{chunk}\n```")
        else:
            embed = discord.Embed(
                title=f"📄 {target_user.display_name}님의 데이터",
                description=f"```json\n{data_str}\n```",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)

    @view_user_data.error
    async def view_user_data_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("이 명령어는 봇 소유자만 사용할 수 있습니다.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("사용법: `!데이터조회 @유저이름`")
        else:
            print(f"!데이터조회 명령어 오류 발생: {error}") # 터미널에 상세 오류 출력
            await ctx.send("명령어 처리 중 알 수 없는 오류가 발생했습니다.")



    @commands.command(name="성장관리")
    @commands.is_owner() # 봇 소유자만 실행 가능
    async def manage_growth(self, ctx, target_name: str, stat_type: str, value_str: str):
        """[관리자용] 등록된 이름으로 유저의 스탯을 관리합니다."""
        
        all_data = load_data()
        
        # 1. 이름으로 플레이어 찾기
        target_id = None
        target_data = None
        for player_id, player_info in all_data.items():
            if player_info.get("name") == target_name:
                target_id = player_id
                target_data = player_info
                break
        
        if not target_data:
            return await ctx.send(f"'{target_name}' 이름을 가진 플레이어를 찾을 수 없습니다.")

        # 2. 스탯 종류 확인
        stat_map = {"정신": "mental", "육체": "physical"}
        if stat_type not in stat_map:
            return await ctx.send("잘못된 스탯 종류입니다. `정신` 또는 `육체` 중에서 선택해주세요.")
        
        stat_key = stat_map[stat_type]

        # 3. 값 파싱 (+/- 숫자)
        try:
            sign = value_str[0]
            amount = int(value_str[1:])
            if sign not in ['+', '-']:
                raise ValueError
        except (ValueError, IndexError):
            return await ctx.send("잘못된 값 형식입니다. `+5`, `-10` 과 같은 형식으로 입력해주세요.")

        # 4. 스탯 수정 및 저장
        original_stat = target_data.get(stat_key, 0)
        
        if sign == '+':
            new_stat = original_stat + amount
        else: # '-'
            new_stat = max(0, original_stat - amount) # 스탯이 0 미만이 되지 않도록 보정

        all_data[target_id][stat_key] = new_stat
        save_data(all_data)

        # 5. 결과 알림
        embed = discord.Embed(
            title="🛠️ 스탯 관리 완료",
            description=f"**{target_name}**님의 스탯을 성공적으로 수정했습니다.",
            color=discord.Color.blue()
        )
        embed.add_field(name="대상", value=target_name, inline=True)
        embed.add_field(name="스탯 종류", value=stat_type, inline=True)
        embed.add_field(name="변경 내용", value=f"`{original_stat}` → `{new_stat}` ({value_str})", inline=False)
        await ctx.send(embed=embed)


    @manage_growth.error
    async def manage_growth_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("이 명령어는 봇 소유자만 사용할 수 있습니다.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("사용법: `!성장관리 [이름] [스탯종류] [+혹은-숫자]`\n> 예시: `!성장관리 홍길동 정신 +5`")

    



# cogs/growth.py 의 GrowthCog 클래스 내부에 추가

    @commands.command(name="직업변경")
    @commands.is_owner()
    async def change_base_class(self, ctx, target_name: str, *, new_base_class: str):
        """[관리자용] 유저를 기본 직업 중 하나로 되돌립니다."""
        
        all_data = load_data()
        
        # 1. 이름으로 플레이어 찾기
        target_id, target_data = None, None
        for player_id, player_info in all_data.items():
            if player_info.get("name") == target_name.strip('"'):
                target_id = player_id
                target_data = player_info
                break
        
        if not target_data:
            return await ctx.send(f"'{target_name}' 이름을 가진 플레이어를 찾을 수 없습니다.")

        # 2. 변경하려는 기본 직업이 유효한지 확인
        if new_base_class not in self.CLASSES:
            valid_classes = ", ".join(f"`{c}`" for c in self.CLASSES)
            return await ctx.send(f"잘못된 기본 직업입니다. {valid_classes} 중에서 선택해주세요.")

        # 3. 데이터 업데이트 (전직 정보 초기화)
        old_class = target_data.get("class", "없음")
        
        all_data[target_id]["class"] = new_base_class
        all_data[target_id]["advanced_class"] = None
        all_data[target_id]["attribute"] = None
        save_data(all_data)

        # 4. 결과 알림
        embed = discord.Embed(
            title="🔄 직업 변경 완료",
            description=f"**{target_name}**님의 직업을 성공적으로 변경했습니다.",
            color=discord.Color.orange()
        )
        embed.add_field(name="대상", value=target_name, inline=True)
        embed.add_field(name="변경 내용", value=f"`{old_class}` → `{new_base_class}` (기본 직업)", inline=False)
        embed.set_footer(text="상위 직업 및 속성 정보가 초기화되었습니다.")
        await ctx.send(embed=embed)

    @change_base_class.error
    async def change_bc_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("이 명령어는 봇 소유자만 사용할 수 있습니다.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("사용법: `!직업변경 [이름] [새로운 기본직업]`\n> 예시: `!직업변경 홍길동 마법사`")

# cogs/growth.py 의 GrowthCog 클래스 내부

# cogs/growth.py 의 GrowthCog 클래스 내부

    @commands.command(name="데이터점검")
    @commands.is_owner()
    async def fix_data_structure(self, ctx):
        """[관리자용] 모든 유저 데이터의 구조를 최신 상태로 업데이트하고 정리합니다."""
        await ctx.send("모든 유저 데이터 구조 점검 및 업데이트를 시작합니다...")
        
        all_data = load_data()
        updated_users = 0
        today_kst_str = datetime.now(self.KST).strftime('%Y-%m-%d')

        for player_id, player_data in all_data.items():
            is_updated_this_loop = False
            
            # ▼▼▼ 'updated'를 'is_updated_this_loop'로 통일했습니다 ▼▼▼
            if 'timezone' not in player_data:
                player_data.setdefault('timezone', None)
                is_updated_this_loop = True

            if 'last_goal_date' in player_data and 'daily_goal_info' not in player_data:
                last_date = player_data['last_goal_date']
                count = 1 if last_date == today_kst_str else 0
                player_data['daily_goal_info'] = {'date': last_date, 'count': count}
                del player_data['last_goal_date']
                is_updated_this_loop = True

            if 'last_daily_reset_date' not in player_data:
                player_data.setdefault('last_daily_reset_date', "2000-01-01")
                is_updated_this_loop = True

            if 'attribute' not in player_data:
                player_data.setdefault('attribute', None)
                is_updated_this_loop = True
            
            if is_updated_this_loop:
                updated_users += 1

        save_data(all_data)
        await ctx.send(f"✅ 완료! 총 {len(all_data)}명의 유저 중 {updated_users}명의 데이터 구조를 업데이트했습니다.")


# 봇에 Cog를 추가하기 위한 필수 함수
async def setup(bot):
    await bot.add_cog(GrowthCog(bot))
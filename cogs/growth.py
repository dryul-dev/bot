# cogs/growth.py

import discord
from discord.ext import commands
import json
import os
from datetime import datetime, time, timedelta, timezone

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
        self.ADVANCED_CLASSES = {
            "마법사": {"Wit": "캐스터", "Heart": "힐러"},
            "마검사": {"Gut": "헌터", "Wit": "조커"},
            "검사": {"Gut": "워리어", "Heart": "디펜더"}
        }

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
            await ctx.send(f"직업을 선택해주세요. (선택 후 변경 불가)\n> `{'`, `'.join(CLASSES)}`")
            msg = await bot.wait_for('message', check=check, timeout=60.0)
            if msg.content not in CLASSES:
                await ctx.send("잘못된 직업입니다. 등록을 다시 시작해주세요.")
                return
            player_class = msg.content
            
            await ctx.send(f"**{player_class}**을(를) 선택하셨습니다. 확정하시겠습니까? (`예` 또는 `아니오`)")
            msg = await bot.wait_for('message', check=check, timeout=30.0)
            if msg.content.lower() != '예':
                await ctx.send("등록이 취소되었습니다.")
                return

            # 이름, 이모지, 색상 입력
            await ctx.send("사용할 이름을 입력해주세요.")
            name_msg = await bot.wait_for('message', check=check, timeout=60.0)
            
            await ctx.send("맵에서 자신을 나타낼 대표 이모지를 하나 입력해주세요.")
            emoji_msg = await bot.wait_for('message', check=check, timeout=60.0)

            await ctx.send("대표 색상을 HEX 코드로 입력해주세요. (예: `#FFFFFF`)")
            color_msg = await bot.wait_for('message', check=check, timeout=60.0)

            all_data[player_id] = {
                "mental": 0, "physical": 0, "challenge_type": None, "challenge_registered_today": False,
                "registered": True, "class": player_class, "name": name_msg.content, 
                "emoji": emoji_msg.content, "color": color_msg.content, "attribute": None,
                "advanced_class": None
            }
            save_data(all_data)
            await ctx.send("🎉 등록이 완료되었습니다!")

        except asyncio.TimeoutError:
            await ctx.send("시간이 초과되어 등록이 취소되었습니다.")
        pass

    @commands.command(name="스탯조회")
    async def check_stats(self, ctx, member: discord.Member = None):
        """자신 또는 다른 플레이어의 프로필과 스탯 정보를 확인합니다."""
        
        # 멘션된 유저가 없으면, 명령어를 사용한 유저를 대상으로 설정
        target_user = member or ctx.author
        
        player_id = str(target_user.id)
        all_data = load_data()

        if player_id not in all_data or not all_data[player_id].get("registered", False):
            await ctx.send(f"**{target_user.display_name}**님은 아직 `!등록`하지 않은 플레이어입니다.")
            return
        
        player_data = all_data[player_id]
        
        # 스탯 계산
        mental = player_data['mental']
        physical = player_data['physical']
        total_stats = mental + physical
        level = 1 + total_stats // 5
        progress = total_stats % 5
        progress_bar = '■ ' * progress + '□ ' * (5 - progress)

        # Embed 생성
        embed = discord.Embed(
            title=f"{player_data['name']}님의 프로필 및 스탯 정보",
            color=int(player_data['color'][1:], 16)
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)
        
        # 프로필 정보 필드
        embed.add_field(name="칭호", value=player_data['class'], inline=True)
        embed.add_field(name="레벨", value=f"**{level}**", inline=True)
        embed.add_field(name="대표 이모지", value=player_data['emoji'], inline=True)
        
        # 스탯 정보 필드
        embed.add_field(name="🧠 정신", value=f"`{mental}`", inline=True)
        embed.add_field(name="💪 육체", value=f"`{physical}`", inline=True)
        embed.add_field(name="🔥 총 스탯", value=f"`{total_stats}`", inline=True)

        # 레벨업 진행도 필드
        embed.add_field(
            name=f"📊 다음 레벨까지 ({progress}/5)",
            value=f"**{progress_bar}**",
            inline=False
        )
        
        await ctx.send(embed=embed)
        pass

    @commands.command(name="정보수정")
    async def edit_info(self, ctx, item: str, *, value: str):
        player_id = str(ctx.author.id)
        all_data = load_data()
        if player_id not in all_data or not all_data[player_id].get("registered", False):
            await ctx.send("먼저 `!등록`을 진행해주세요.")
            return

        editable_items = {"이름": "name", "이모지": "emoji", "컬러": "color"}
        if item not in editable_items:
            await ctx.send("수정할 수 있는 항목은 `이름`, `이모지`, `컬러` 입니다.")
            return
        
        key = editable_items[item]
        all_data[player_id][key] = value
        save_data(all_data)
        await ctx.send(f"'{item}' 정보가 '{value}' (으)로 성공적으로 변경되었습니다.")

    # --- 스탯 성장 명령어 (기존 코드 개선) ---
    # ... (이전 답변의 !정신도전, !육체도전, !도전완료 코드와 동일하게 작동하므로 생략)
    # ... 필요하시면 해당 부분을 여기에 붙여넣으시면 됩니다.

    # --- 플레이어 정보 및 스탯 성장 명령어 ---


        """자신의 이름, 이모지, 컬러 정보를 수정합니다."""
        player_id = str(ctx.author.id)
        all_data = load_data()
        if player_id not in all_data or not all_data[player_id].get("registered", False):
            await ctx.send("먼저 `!등록`을 진행해주세요.")
            return

        editable_items = {"이름": "name", "이모지": "emoji", "컬러": "color"}
        if item not in editable_items:
            await ctx.send("수정할 수 있는 항목은 `이름`, `이모지`, `컬러` 입니다.")
            return
        
        key = editable_items[item]
        all_data[player_id][key] = value
        save_data(all_data)
        await ctx.send(f"'{item}' 정보가 '{value}' (으)로 성공적으로 변경되었습니다.")
        pass

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
            await bot.wait_for('message', check=check, timeout=30.0)
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
            'rest_buff_active': False
        }
        # ▲▲▲ 여기가 수정된 부분입니다 ▲▲▲
        
        save_data(all_data)
        
        # 3단계: 완료 메시지 전송
        await ctx.send(f"✅ **{ctx.author.display_name}**님의 모든 데이터가 성공적으로 초기화되었습니다. `!등록` 명령어를 사용해 새로운 여정을 시작하세요!")
        """자신의 프로필 정보(직업, 이름 등)를 모두 초기화합니다. (스탯은 유지)"""
        pass

    @commands.command(name="전직")
    async def advance_class(self, ctx):
        """5레벨 도달 시 상위 직업으로 전직합니다."""
        player_id = str(ctx.author.id)
        all_data = load_data()
        player_data = all_data.get(player_id)

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")
        
        if player_data.get("advanced_class"):
            return await ctx.send(f"이미 **{player_data['advanced_class']}**(으)로 전직하셨습니다.")

        level = 1 + ((player_data['mental'] + player_data['physical']) // 5)
        if level < 5:
            return await ctx.send(f"전직은 5레벨부터 가능합니다. (현재 레벨: {level})")

        base_class = player_data.get("class")
        options = ADVANCED_CLASSES.get(base_class)
        if not options:
            return await ctx.send("오류: 유효하지 않은 기본 직업입니다.")

        option_list = [f"`{name}` ({attr})" for attr, name in options.items()]
        await ctx.send(f"**{ctx.author.display_name}**님, 전직할 상위 클래스를 선택해주세요.\n> {', '.join(option_list)}")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content in options.values()

        try:
            msg = await bot.wait_for('message', check=check, timeout=60.0)
            chosen_class = msg.content
            
            # 선택한 직업으로부터 속성 찾기
            chosen_attribute = [attr for attr, name in options.items() if name == chosen_class][0]

            player_data["advanced_class"] = chosen_class
            player_data["attribute"] = chosen_attribute
            save_data(all_data)

            await ctx.send(f"🎉 축하합니다! **{chosen_class}**(으)로 전직했습니다! 이제 `{chosen_attribute}` 속성을 가지며 `!스킬` 명령어를 사용할 수 있습니다.")

        except asyncio.TimeoutError:
            await ctx.send("시간이 초과되어 전직이 취소되었습니다.")
            pass

    @commands.command(name="정신도전")
    async def register_mental_challenge(self, ctx):
        """오전 6시~14시 사이에 오늘의 정신 도전을 등록합니다."""
        now_kst = datetime.now(KST).time()
        if not (time(6, 0) <= now_kst < time(14, 0)):
            embed = discord.Embed(title="❌ 도전 등록 실패", description=f"**도전 등록은 KST 기준 오전 6시부터 오후 2시까지만 가능합니다.**\n(현재 시간: {now_kst.strftime('%H:%M')})", color=discord.Color.red())
            await ctx.send(embed=embed)
            return

        all_data = load_data()
        player_id = str(ctx.author.id)
        if player_id not in all_data:
            all_data[player_id] = {"mental": 0, "physical": 0, "challenge_type": None, "challenge_registered_today": False}
        player_data = all_data[player_id]

        if player_data.get("challenge_registered_today", False):
            action_type = player_data.get("challenge_type", "활동")
            embed = discord.Embed(title="⚠️ 이미 오늘의 활동을 마쳤습니다", description=f"오늘은 이미 **'{action_type}'**을(를) 선택하셨습니다.", color=discord.Color.orange())
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
        """오전 6시~14시 사이에 오늘의 육체 도전을 등록합니다."""
        now_kst = datetime.now(KST).time()
        if not (time(6, 0) <= now_kst < time(14, 0)):
            embed = discord.Embed(title="❌ 도전 등록 실패", description=f"**도전 등록은 KST 기준 오전 6시부터 오후 2시까지만 가능합니다.**\n(현재 시간: {now_kst.strftime('%H:%M')})", color=discord.Color.red())
            await ctx.send(embed=embed)
            return

        all_data = load_data()
        player_id = str(ctx.author.id)
        if player_id not in all_data:
            all_data[player_id] = {"mental": 0, "physical": 0, "challenge_type": None, "challenge_registered_today": False}
        player_data = all_data[player_id]

        if player_data.get("challenge_registered_today", False):
            action_type = player_data.get("challenge_type", "활동")
            embed = discord.Embed(title="⚠️ 이미 오늘의 활동을 마쳤습니다", description=f"오늘은 이미 **'{action_type}'**을(를) 선택하셨습니다.", color=discord.Color.orange())
            await ctx.send(embed=embed)
            return

        player_data["challenge_type"] = "육체도전"
        player_data["challenge_registered_today"] = True
        save_data(all_data)
        
        embed = discord.Embed(title="💪 '육체' 도전 등록 완료!", description=f"**{ctx.author.display_name}**님, 오늘의 '육체' 도전이 정상적으로 등록되었습니다.", color=discord.Color.gold())
        embed.add_field(name="진행 안내", value="오후 4시 이후 `!도전완료` 명령어를 통해\n결과를 보고하고 스탯을 획득하세요!", inline=False)
        embed.set_footer(text="강인한 육체에 강인한 정신이 깃듭니다.")
        await ctx.send(embed=embed)
        pass

    @commands.command(name="도전완료")
    async def complete_challenge(self, ctx):
        """오후 16시~02시 사이에 등록한 도전을 완료하고 스탯을 얻습니다."""
        now_kst = datetime.now(KST)
        if not (now_kst.hour >= 16 or now_kst.hour < 2): 
            embed = discord.Embed(title="❌ 도전 완료 실패", description=f"**도전 완료는 KST 기준 오후 4시부터 새벽 2시까지만 가능합니다.**\n(현재 시간: {now_kst.strftime('%H:%M')})", color=discord.Color.red())
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
            stat_name, emoji, color = "육체", "💪", discord.Color.gold()
        
        # 완료 처리: challenge_type을 None으로 바꿔 중복 완료 방지
        player_data["challenge_type"] = None
        save_data(all_data)
        
        embed = discord.Embed(title=f"{emoji} 도전 성공! {stat_name} 스탯 상승!", description=f"**{ctx.author.display_name}**님, 오늘의 도전을 성공적으로 완수했습니다.", color=color)
        embed.add_field(name="획득 스탯", value=f"**{stat_name} +1**", inline=False)
        await ctx.send(embed=embed)

        # `!스탯조회` 함수가 코드 내에 정의되어 있어야 합니다.
        await check_stats(ctx, member=None)
        pass

    @commands.command(name="휴식")
    async def take_rest(self, ctx):
        """오전 6시~14시 사이에 오늘의 도전을 쉬고, 다음 전투를 위한 버프를 받습니다."""
        now_kst = datetime.now(KST).time()
        if not (time(6, 0) <= now_kst < time(14, 0)):
            embed = discord.Embed(title="❌ 휴식 선언 실패", description=f"**휴식은 KST 기준 오전 6시부터 오후 2시까지만 선택할 수 있습니다.**\n(현재 시간: {now_kst.strftime('%H:%M')})", color=discord.Color.red())
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
        pass


# 봇에 Cog를 추가하기 위한 필수 함수
async def setup(bot):
    await bot.add_cog(GrowthCog(bot))
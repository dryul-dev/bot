# cogs/school.py (최종 수정 버전)

import discord
from discord.ext import commands
import json
import os
import asyncio
import random

# --- 데이터 관리 함수 ---
def load_data():
    if not os.path.exists("player_data.json"): return {}
    with open("player_data.json", 'r', encoding='utf-8') as f: return json.load(f)

def save_data(data):
    with open("player_data.json", 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

# --- 아이템 정보 (모든 이름에서 띄어쓰기 제거) ---
SHOP_ITEMS = {
    "알사탕": {"price": 5, "description": "없는 맛이 없는 알사탕. 주머니에 넣어두면 마음이 든든하다."},
    "꽃송이": {"price": 10, "description": "감성 한 움큼을 당신에게. 누군가에게 선물하기에 좋다."},
    "몬스터포션": {"price": 15, "description": "지친 학생들을 위한 에너지 포션."},
    "아카데미수건": {"price": 20, "description": "프라이드와 실용성을 한 번에. 땀을 닦아도, 눈물을 닦아도 좋다."},
    "인형": {"price": 30, "description": "무엇을 닮았을까? 아마 당신이 원하는 그 모양이다."},
    "드림캐쳐": {"price": 50, "description": "하루의 마무리에 편안한 쉼이 함께하기를. 그리고 또 내일 만나기를."},
    "홀케이크": {"price": 80, "description": "소중한 사람을 향한 달콤한 축하. 특별한 날을 기념하기에 좋다."},
    "교내방송발언권": {"price": 100, "description": "이 정도 가격이면 모범생들만 사용하겠지? 전교생에게 하고 싶은 말을 할 수 있다."},
    "???": {"price": 200, "description": "정체를 알 수 없는 수상한 물약. 마시면 어떻게 될까?"}
}
PERMANENT_ITEMS = {"아카데미 수건", "인형", "드림캐쳐"}
ITEM_USAGE_TEXT = {
    "알사탕": "입 안에서 도르륵 굴려본다. 작지만 확실한 행복감이 느껴진다.",
    "꽃송이": "한 송이 꽃을 가만히 바라본다. 은은한 향기가 코 끝을 간지럽힌다.",
    "아카데미수건": "열심히 닦고 나니 뽀송하고 개운하다!",
    "인형": "부들부들한 감촉을 만끽하니 긴장이 풀어진다.",
    "드림캐쳐": "오늘 밤은 좋은 꿈을 꿀 수 있을 것 같다.",
    "홀케이크": "혼자 먹기엔 너무 크다. 다같이 나눠먹자!",
    "교내방송발언권": "이제 당신이 방송실에 가는 걸 막을 사람은 아무도 없다.",
    "???": [
        "…시야가 낮아졌다? (24시간 동안 키 20cm 감소.)",
        "머리카락이 바닥에 쓸릴 정도로 자라났다...! (24시간 동안 머리카락 길이 3m.)",
        "멍멍왈왈크르릉컹? (24시간 동안 강아지 언어 구사.)",
        "... 나에게서 빛이 난다. (24시간 동안 발광 지속.)",
        "평소와 기분이 다르다? (24시간 동안 성격 반전.)"
        ],
    "몬스터포션": [
        "검은 포장의 몬스터 포션. 두뇌 회전이 빨라진 게 느껴진다!",
        "하얀 포장의 몬스터 포션. 운동 신경이 활성화된 게 느껴진다!",
        "분홍 포장의 몬스터 포션. ...특별한 효과는 없지만 매우 맛있다!"
        ]
}

class SchoolCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot



    @commands.command(name="주머니")
    async def pocket(self, ctx):
        all_data = load_data()
        player_data = all_data.get(str(ctx.author.id))
        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")

        points = player_data.get("school_points", 0)
        inventory = player_data.get("inventory", [])
        
        embed = discord.Embed(title=f"🎒 {player_data['name']}의 주머니", color=int(player_data['color'][1:], 16))
        embed.add_field(name="🎓 스쿨 포인트", value=f"`{points}` P", inline=False)
        item_list = "\n".join(f"- {item}" for item in inventory) if inventory else "아직 아이템이 없습니다."
        embed.add_field(name=f"📦 보유 아이템 ({len(inventory)}/8)", value=item_list, inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="교내상점")
    async def shop(self, ctx):
        embed = discord.Embed(title="🏪 교내 상점", description="`!구매 [아이템이름]`으로 물건을 구매할 수 있습니다.", color=0x00308F)
        for name, data in SHOP_ITEMS.items():
            embed.add_field(name=f"{name}", value=f"> `{data['price']}` P", inline=True)
        embed.set_footer(text="남은 청춘을 즐겨라, 아해들아!")
        await ctx.send(embed=embed)

    @commands.command(name="구매")
    async def buy_item(self, ctx, *, item_name_input: str):
        item_name = item_name_input.replace(" ", "") # 입력값의 띄어쓰기 제거
        if item_name not in SHOP_ITEMS:
            return await ctx.send("교내상점에서 판매하지 않는 아이템입니다. (시장의 경우 `!시장구매`)")
        
        all_data = load_data()
        player_data = all_data.get(str(ctx.author.id))
        if not player_data: return await ctx.send("먼저 `!등록`을 진행해주세요.")

        item_info = SHOP_ITEMS[item_name]
        points = player_data.get("school_points", 0)
        inventory = player_data.get("inventory", [])

        if len(inventory) >= 8: return await ctx.send("주머니가 가득 차서 더 이상 아이템을 구매할 수 없습니다.")
        if points < item_info['price']: return await ctx.send("스쿨 포인트가 부족합니다.")

        embed = discord.Embed(title="🛒 구매 확인", description=item_info['description'], color=int(player_data['color'][1:], 16))
        embed.add_field(name="아이템", value=item_name, inline=True); embed.add_field(name="가격", value=f"`{item_info['price']}` P", inline=True); embed.add_field(name="구매 후 포인트", value=f"`{points - item_info['price']}` P", inline=True)
        embed.set_footer(text="구매하시려면 30초 안에 '예'를 입력해주세요.")
        await ctx.send(embed=embed)

        def check(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == '예'
        try: await self.bot.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError: return await ctx.send("시간이 초과되어 구매가 취소되었습니다.")

        player_data['school_points'] -= item_info['price']
        inventory.append(item_name)
        player_data['inventory'] = inventory
        save_data(all_data)
        await ctx.send(f"**{item_name}** 구매를 완료했습니다!")

    @commands.command(name="버리기")
    async def discard_item(self, ctx, *, item_name_input: str):

        item_name = item_name_input.replace(" ", "")
        all_data = load_data()
        player_data = all_data.get(str(ctx.author.id))
        if not player_data: return await ctx.send("먼저 `!등록`을 진행해주세요.")

        inventory = player_data.get("inventory", [])
        if item_name not in inventory: return await ctx.send(f"'{item_name}' 아이템을 가지고 있지 않습니다.")

        embed = discord.Embed(title="🗑️ 아이템 버리기 확인", description=f"정말로 **{item_name}** 아이템을 버리시겠습니까?\n버린 아이템은 되찾을 수 없습니다.", color=discord.Color.red())
        embed.set_footer(text="동의하시면 30초 안에 '예'를 입력해주세요.")
        await ctx.send(embed=embed)

        def check(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == '예'
        try: await self.bot.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError: return await ctx.send("시간이 초과되어 아이템 버리기가 취소되었습니다.")

        inventory.remove(item_name)
        player_data["inventory"] = inventory
        save_data(all_data)
        await ctx.send(f"**{item_name}** 아이템을 성공적으로 버렸습니다.")

    @commands.command(name="선물")
    async def gift_item(self, ctx, target_user: discord.Member, *, item_name_input: str):
        item_name = item_name_input.replace(" ", "")
        if ctx.author == target_user: return await ctx.send("자기 자신에게는 선물을 보낼 수 없습니다.")
            
        all_data = load_data()
        sender_data, receiver_data = all_data.get(str(ctx.author.id)), all_data.get(str(target_user.id))
        if not sender_data or not receiver_data: return await ctx.send("선물을 보내거나 받는 사람 중 등록되지 않은 유저가 있습니다.")

        sender_inventory = sender_data.get("inventory", [])
        if item_name not in sender_inventory: return await ctx.send(f"'{item_name}' 아이템을 가지고 있지 않습니다.")

        receiver_inventory = receiver_data.get("inventory", [])
        if len(receiver_inventory) >= 8: return await ctx.send(f"{target_user.display_name}님의 주머니가 가득 차서 선물을 보낼 수 없습니다.")
        
        sender_inventory.remove(item_name)
        receiver_inventory.append(item_name)
        save_data(all_data)
        await ctx.send(f"🎁 {target_user.display_name}님에게 **{item_name}**을(를) 선물했습니다!")

    @commands.command(name="사용")
    async def use_item(self, ctx, *, item_name_input: str):
        item_name = item_name_input.replace(" ", "")
        all_data = load_data()
        player_data = all_data.get(str(ctx.author.id))
        if not player_data: return await ctx.send("먼저 `!등록`을 진행해주세요.")

        inventory = player_data.get("inventory", [])
        if item_name not in inventory: return await ctx.send(f"'{item_name}' 아이템을 가지고 있지 않습니다.")
        
        usage_text_source = ITEM_USAGE_TEXT.get(item_name)
        if isinstance(usage_text_source, list):
            usage_text = random.choice(usage_text_source)
        else:
            usage_text = usage_text_source or f"**{item_name}**을(를) 어떻게 사용해야 할지 감이 오지 않는다..."

        embed = discord.Embed(description=usage_text, color=int(player_data['color'][1:], 16))
        
        if item_name not in PERMANENT_ITEMS:
            inventory.remove(item_name)
            save_data(all_data)
            embed.set_footer(text=f"사용한 {item_name} 아이템이 사라졌습니다.")
        await ctx.send(embed=embed)

        # cogs/school.py 의 SchoolCog 클래스 내부에 추가

    @commands.command(name="포인트관리")
    @commands.is_owner() # 봇 소유자만 실행 가능
    async def manage_school_points(self, ctx, target_name: str, value_str: str):
        """[관리자용] 등록된 이름으로 유저의 스쿨 포인트를 관리합니다."""
        
        all_data = load_data()
        
        # 1. 이름으로 플레이어 찾기
        target_id = None
        target_data = None
        for player_id, player_info in all_data.items():
            # 이름에 띄어쓰기가 있는 경우를 대비해 따옴표를 제거
            if player_info.get("name") == target_name.strip('"'):
                target_id = player_id
                target_data = player_info
                break
        
        if not target_data:
            return await ctx.send(f"'{target_name}' 이름을 가진 플레이어를 찾을 수 없습니다.")

        # 2. 값 파싱 (+/- 숫자)
        try:
            sign = value_str[0]
            amount = int(value_str[1:])
            if sign not in ['+', '-']:
                raise ValueError
        except (ValueError, IndexError):
            return await ctx.send("잘못된 값 형식입니다. `+50`, `-30` 과 같은 형식으로 입력해주세요.")

        # 3. 스쿨 포인트 수정 및 저장
        original_points = target_data.get('school_points', 0)
        
        if sign == '+':
            new_points = original_points + amount
        else: # '-'
            new_points = max(0, original_points - amount) # 포인트가 0 미만이 되지 않도록 보정

        all_data[target_id]['school_points'] = new_points
        save_data(all_data)

        # 4. 결과 알림
        embed = discord.Embed(
            title="🎓 포인트 관리 완료",
            description=f"**{target_name}**님의 스쿨 포인트를 성공적으로 수정했습니다.",
            color=discord.Color.green()
        )
        embed.add_field(name="대상", value=target_name, inline=True)
        embed.add_field(name="변경 내용", value=f"`{original_points}` → `{new_points}` ({value_str}P)", inline=False)
        await ctx.send(embed=embed)

    @manage_school_points.error
    async def manage_school_points_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("이 명령어는 봇 소유자만 사용할 수 있습니다.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("사용법: `!포인트관리 [이름] [+혹은-숫자]`\n> 예시: `!포인트관리 홍길동 +100`")

async def setup(bot):
    await bot.add_cog(SchoolCog(bot))
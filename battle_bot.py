import discord
from discord.ext import commands, tasks
import json
import os
import random
import asyncio
from datetime import datetime, time, timedelta, timezone
from config import DISCORD_TOKEN

# --- 봇 기본 설정 ---

BOT_PREFIX = "!"
DATA_FILE = "player_data.json"
KST = timezone(timedelta(hours=9))
CLASSES = ["마법사", "마검사", "검사"]

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

# --- 전역 변수 ---
# 현재 진행중인 모든 전투를 관리합니다. {채널ID: Battle객체}
active_battles = {}

# --- 데이터 관리 함수 ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- 핵심: 전투 관리 클래스 ---
class Battle:
    def __init__(self, channel, player1, player2):
        self.channel = channel
        self.p1_user = player1
        self.p2_user = player2
        self.grid = ["□"] * 15
        self.turn_timer = None
        self.battle_log = ["전투가 시작되었습니다!"]
        all_data = load_data()
        self.p1_stats = self._setup_player_stats(all_data, self.p1_user)
        self.p2_stats = self._setup_player_stats(all_data, self.p2_user)
        positions = random.sample([0, 14], 2)
        self.p1_stats['pos'] = positions[0]
        self.p2_stats['pos'] = positions[1]
        self.grid[self.p1_stats['pos']] = self.p1_stats['emoji']
        self.grid[self.p2_stats['pos']] = self.p2_stats['emoji']
        self.current_turn_player = random.choice([self.p1_user, self.p2_user])
        self.turn_actions_left = 2

    def _setup_player_stats(self, all_data, user):
        player_id = str(user.id)
        base_stats = all_data[player_id]
        level = 1 + (base_stats['mental'] + base_stats['physical']) // 5
        max_hp = max(1, level * 10 + base_stats['physical']) # 최소 체력 1 보장
        
        return {
            "id": user.id, "name": base_stats['name'], "emoji": base_stats['emoji'], "class": base_stats['class'],
            "color": int(base_stats['color'][1:], 16), "mental": base_stats['mental'], "physical": base_stats['physical'],
            "level": level, "max_hp": max_hp, "current_hp": max_hp, "pos": -1, "special_cooldown": 0, "double_damage_buff": False
        }

    def get_player_stats(self, user): return self.p1_stats if user.id == self.p1_user.id else self.p2_stats
    def get_opponent_stats(self, user): return self.p2_stats if user.id == self.p1_user.id else self.p1_stats

    def add_log(self, message):
        self.battle_log.append(message)
        if len(self.battle_log) > 5: self.battle_log.pop(0)

    async def display_board(self, extra_message=""):
        turn_player_stats = self.get_player_stats(self.current_turn_player)
        embed = discord.Embed(title="⚔️ 전투 진행중 ⚔️", description=f"**현재 턴: {turn_player_stats['name']}** (`!이동`, `!공격`, `!특수`)", color=turn_player_stats['color'])
        grid_str = ""
        for i, cell in enumerate(self.grid):
            grid_str += f" `{cell}` "
            if (i + 1) % 5 == 0: grid_str += "\n"
        embed.add_field(name="[ 전투 맵 ]", value=grid_str, inline=False)
        for p_stats in [self.p1_stats, self.p2_stats]:
            hp_bar = "❤️" * int(p_stats['current_hp'] / p_stats['max_hp'] * 10)
            hp_bar += "🖤" * (10 - len(hp_bar))
            embed.add_field(name=f"{p_stats['emoji']} {p_stats['name']} ({p_stats['class']})", value=f"HP: {p_stats['current_hp']}/{p_stats['max_hp']}\n{hp_bar}", inline=True)
        embed.add_field(name="남은 행동", value=f"{self.turn_actions_left}회", inline=True)
        embed.add_field(name="📜 전투 로그", value="\n".join(self.battle_log), inline=False)
        if extra_message: embed.set_footer(text=extra_message)
        await self.channel.send(embed=embed)

    async def handle_action_cost(self, cost=1):
        self.turn_actions_left -= cost
        if self.turn_actions_left <= 0:
            await self.display_board("행동력을 모두 소모하여 턴을 종료합니다.")
            await asyncio.sleep(2)
            await self.next_turn()
        else:
            await self.display_board()

    async def next_turn(self):
        p_stats = self.get_player_stats(self.current_turn_player)
        if p_stats['special_cooldown'] > 0: p_stats['special_cooldown'] -= 1
        self.current_turn_player = self.p2_user if self.current_turn_player.id == self.p1_user.id else self.p1_user
        self.turn_actions_left = 2
        self.add_log(f"▶️ {self.get_player_stats(self.current_turn_player)['name']}의 턴입니다.")
        await self.start_turn_timer()
        await self.display_board()

    async def start_turn_timer(self):
        if self.turn_timer: self.turn_timer.cancel()
        self.turn_timer = asyncio.create_task(self.timeout_task())

    async def timeout_task(self):
        try:
            await asyncio.sleep(300) # 5분
            winner = self.get_opponent_stats(self.current_turn_player)
            loser = self.get_player_stats(self.current_turn_player)
            await self.end_battle(winner, f"시간 초과로 {loser['name']}님이 패배했습니다.")
        except asyncio.CancelledError: pass

    async def end_battle(self, winner_stats, reason):
        if self.turn_timer: self.turn_timer.cancel()
        embed = discord.Embed(title="🎉 전투 종료! 🎉", description=f"**승자: {winner_stats['name']}**\n> {reason}", color=winner_stats['color'])
        await self.channel.send(embed=embed)
        if self.channel.id in active_battles: del active_battles[self.channel.id]
        
    def get_coords(self, pos): return pos // 5, pos % 5
    def get_distance(self, pos1, pos2):
        r1, c1 = self.get_coords(pos1); r2, c2 = self.get_coords(pos2)
        return max(abs(r1 - r2), abs(c1 - c2))

# --- 봇 이벤트 및 작업 루프 ---
@bot.event
async def on_ready():
    print(f'{bot.user.name} 봇이 성공적으로 로그인했습니다!')
    daily_reset_task.start()

@tasks.loop(minutes=1)
async def daily_reset_task():
    now = datetime.now(KST)
    if now.hour == 0 and now.minute == 0:
        all_data = load_data()
        for player_id in all_data:
            all_data[player_id]["challenge_type"] = None
            all_data[player_id]["challenge_registered_today"] = False
        save_data(all_data)
        print("일일 도전 상태 초기화 완료.")

# --- 플레이어 등록 및 정보 명령어 ---
@bot.command(name="등록")
async def register(ctx):
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
            "emoji": emoji_msg.content, "color": color_msg.content
        }
        save_data(all_data)
        await ctx.send("🎉 등록이 완료되었습니다!")

    except asyncio.TimeoutError:
        await ctx.send("시간이 초과되어 등록이 취소되었습니다.")

@bot.command(name="정보수정")
async def edit_info(ctx, item: str, *, value: str):
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


@bot.command(name="정신도전")
async def register_mental_challenge(ctx):
    """오전 6시~12시 사이에 오늘의 정신 도전을 등록합니다."""
    now_kst = datetime.now(KST).time()
    if not (time(6, 0) <= now_kst < time(12, 0)):
        embed = discord.Embed(title="❌ 도전 등록 실패", description="**도전 등록은 오전 6시부터 12시까지만 가능합니다.**", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    all_data = load_data()
    player_id = str(ctx.author.id)
    # 데이터가 없는 신규 유저를 위한 처리
    if player_id not in all_data:
        all_data[player_id] = {"mental": 0, "physical": 0, "challenge_type": None, "challenge_registered_today": False}

    player_data = all_data[player_id]

    if player_data.get("challenge_registered_today", False):
        challenge = "정신" if player_data.get('challenge_type') == 'mental' else '육체'
        embed = discord.Embed(title="⚠️ 이미 도전이 등록되었습니다", description=f"이미 오늘의 **{challenge} 도전**을 등록하셨습니다.", color=discord.Color.orange())
        await ctx.send(embed=embed)
        return

    player_data["challenge_type"] = "mental"
    player_data["challenge_registered_today"] = True
    save_data(all_data)
    
    embed = discord.Embed(title="🧠 '정신' 도전 등록 완료!", description=f"**{ctx.author.display_name}님, 오늘의 '정신' 도전이 정상적으로 등록되었습니다.**", color=discord.Color.purple())
    embed.add_field(name="진행 안내", value="오후 6시 이후 `!도전완료` 명령어를 통해\n결과를 보고하고 스탯을 획득하세요!", inline=False)
    embed.set_footer(text="꾸준함이 성장의 열쇠입니다.")
    await ctx.send(embed=embed)


@bot.command(name="육체도전")
async def register_physical_challenge(ctx):
    """오전 6시~12시 사이에 오늘의 육체 도전을 등록합니다."""
    now_kst = datetime.now(KST).time()
    if not (time(6, 0) <= now_kst < time(12, 0)):
        embed = discord.Embed(title="❌ 도전 등록 실패", description="**도전 등록은 오전 6시부터 12시까지만 가능합니다.**", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    all_data = load_data()
    player_id = str(ctx.author.id)
    if player_id not in all_data:
        all_data[player_id] = {"mental": 0, "physical": 0, "challenge_type": None, "challenge_registered_today": False}
    
    player_data = all_data[player_id]

    if player_data.get("challenge_registered_today", False):
        challenge = "정신" if player_data.get('challenge_type') == 'mental' else '육체'
        embed = discord.Embed(title="⚠️ 이미 도전이 등록되었습니다", description=f"이미 오늘의 **{challenge} 도전**을 등록하셨습니다.", color=discord.Color.orange())
        await ctx.send(embed=embed)
        return

    player_data["challenge_type"] = "physical"
    player_data["challenge_registered_today"] = True
    save_data(all_data)
    
    embed = discord.Embed(title="💪 '육체' 도전 등록 완료!", description=f"**{ctx.author.display_name}님, 오늘의 '육체' 도전이 정상적으로 등록되었습니다.**", color=discord.Color.gold())
    embed.add_field(name="진행 안내", value="오후 6시 이후 `!도전완료` 명령어를 통해\n결과를 보고하고 스탯을 획득하세요!", inline=False)
    embed.set_footer(text="강인한 육체에 강인한 정신이 깃듭니다.")
    await ctx.send(embed=embed)


@bot.command(name="도전완료")
async def complete_challenge(ctx):
    """오후 18시~24시 사이에 등록한 도전을 완료하고 스탯을 얻습니다."""
    now_kst = datetime.now(KST).time()
    if not (time(18, 0) <= now_kst): 
        embed = discord.Embed(title="❌ 도전 완료 실패", description="**도전 완료는 오후 6시부터 자정까지만 가능합니다.**", color=discord.Color.red())
        await ctx.send(embed=embed)
        return
        
    all_data = load_data()
    player_id = str(ctx.author.id)
    if player_id not in all_data:
        all_data[player_id] = {"mental": 0, "physical": 0, "challenge_type": None, "challenge_registered_today": False}
        
    player_data = all_data[player_id]
    
    if not player_data.get("challenge_registered_today", False):
        embed = discord.Embed(title="🤔 등록된 도전 없음", description="아직 오늘 등록한 도전이 없습니다.\n먼저 `!정신도전` 또는 `!육체도전`을 등록해주세요.", color=discord.Color.light_grey())
        await ctx.send(embed=embed)
        return
    
    if player_data.get("challenge_type") is None:
        embed = discord.Embed(title="✅ 이미 오늘의 도전을 완료했습니다", description="스탯을 이미 받으셨습니다. 내일 다시 도전해주세요!", color=discord.Color.green())
        await ctx.send(embed=embed)
        return
        
    challenge_type = player_data["challenge_type"]
    
    if challenge_type == "mental":
        player_data["mental"] += 1
        stat_name = "정신"; emoji = "🧠"; color = discord.Color.purple()
    elif challenge_type == "physical":
        player_data["physical"] += 1
        stat_name = "육체"; emoji = "💪"; color = discord.Color.gold()
    
    player_data["challenge_type"] = None
    save_data(all_data)
    
    embed = discord.Embed(title=f"{emoji} 도전 성공! {stat_name} 스탯 상승!", description=f"**{ctx.author.display_name}님, 오늘의 도전을 성공적으로 완수했습니다.**", color=color)
    embed.add_field(name="획득 스탯", value=f"**{stat_name} +1**", inline=False)
    await ctx.send(embed=embed)

    # 도전 완료 후 자동으로 스탯 조회를 보여주기 위해 check_stats 함수를 직접 호출
    await check_stats(ctx, member=None)
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
    level = total_stats // 5
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

@bot.command(name="스탯조회")
async def check_stats(ctx, member: discord.Member = None):
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


# --- 전투 명령어 ---
@bot.command(name="대결")
async def battle_request(ctx, opponent: discord.Member):
    if ctx.author == opponent:
        await ctx.send("자기 자신과는 대결할 수 없습니다.")
        return
    if ctx.channel.id in active_battles:
        await ctx.send("이 채널에서는 이미 전투가 진행중입니다.")
        return

    all_data = load_data()
    p1_id, p2_id = str(ctx.author.id), str(opponent.id)

    if not all_data.get(p1_id, {}).get("registered", False) or \
       not all_data.get(p2_id, {}).get("registered", False):
        await ctx.send("두 플레이어 모두 `!등록`을 완료해야 합니다.")
        return

    # 대결 수락/거절
    msg = await ctx.send(f"{opponent.mention}, {ctx.author.display_name}님의 대결 신청을 수락하시겠습니까? (15초 내 반응)")
    await msg.add_reaction("✅")
    await msg.add_reaction("❌")

    def check(reaction, user):
        return user == opponent and str(reaction.emoji) in ["✅", "❌"]

    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=15.0, check=check)
        if str(reaction.emoji) == "✅":
            await ctx.send("대결이 성사되었습니다! 전투를 시작합니다.")
            battle = Battle(ctx.channel, ctx.author, opponent)
            active_battles[ctx.channel.id] = battle
            await battle.start_turn_timer()
            await battle.display_board()
        else:
            await ctx.send("대결이 거절되었습니다.")
    except asyncio.TimeoutError:
        await ctx.send("시간이 초과되어 대결이 취소되었습니다.")

# --- 전투 명령어 (기능 완성) ---
@bot.command(name="이동")
async def move(ctx, *directions):
    battle = active_battles.get(ctx.channel.id)
    if not battle or ctx.author != battle.current_turn_player or battle.turn_actions_left <= 0: return

    p_stats = battle.get_player_stats(ctx.author)
    mobility = 2 if p_stats['class'] == '검사' else 1
    
    if len(directions) != mobility:
        return await ctx.send(f"👉 **{p_stats['class']}**의 이동력은 **{mobility}**입니다. `{mobility}`개의 방향을 입력해주세요. (예: `!이동 w d`)", delete_after=10)

    current_pos = p_stats['pos']
    path = [current_pos]
    
    for direction in directions:
        next_pos = path[-1]
        if direction.lower() == 'w': next_pos -= 5
        elif direction.lower() == 's': next_pos += 5
        elif direction.lower() == 'a': next_pos -= 1
        elif direction.lower() == 'd': next_pos += 1
        
        # 맵 경계 및 좌우 이동 유효성 검사
        if not (0 <= next_pos < 15) or \
           (direction.lower() in 'ad' and path[-1] // 5 != next_pos // 5):
            return await ctx.send("❌ 맵 밖으로 이동할 수 없습니다.", delete_after=10)
        path.append(next_pos)
    
    final_pos = path[-1]
    opponent_pos = battle.get_opponent_stats(ctx.author)['pos']
    if final_pos == opponent_pos:
        return await ctx.send("❌ 상대방이 있는 칸으로 이동할 수 없습니다.", delete_after=10)
    
    # 상태 업데이트
    battle.grid[current_pos] = "□"
    battle.grid[final_pos] = p_stats['emoji']
    p_stats['pos'] = final_pos
    battle.add_log(f"🚶 {p_stats['name']}이(가) 이동했습니다.")
    await battle.handle_action_cost(1)


@bot.command(name="공격")
async def attack(ctx):
    battle = active_battles.get(ctx.channel.id)
    if not battle or ctx.author != battle.current_turn_player or battle.turn_actions_left <= 0: return
    
    attacker = battle.get_player_stats(ctx.author)
    target = battle.get_opponent_stats(ctx.author)
    distance = battle.get_distance(attacker['pos'], target['pos'])

    # 직업별 유효 공격 판정
    can_attack = False
    attack_type = ""
    if attacker['class'] == '마법사' and 3 <= distance <= 5: can_attack, attack_type = True, "원거리"
    elif attacker['class'] == '마검사':
        if distance == 1: can_attack, attack_type = True, "근거리"
        elif 2 <= distance <= 3: can_attack, attack_type = True, "원거리"
    elif attacker['class'] == '검사' and distance == 1: can_attack, attack_type = True, "근거리"

    if not can_attack:
        return await ctx.send("❌ 공격 사거리가 아닙니다.", delete_after=10)
        
    # 데미지 계산
    if attack_type == "원거리":
        damage = attacker['mental'] + random.randint(0, attacker['physical'])
    else: # 근거리
        damage = attacker['physical'] + random.randint(0, attacker['mental'])
    
    # 검사 특수 능력 적용
    if attacker['double_damage_buff']:
        damage *= 2
        attacker['double_damage_buff'] = False
        battle.add_log(f"🔥 {attacker['name']}의 분노의 일격!")

    damage = max(1, damage) # 최소 데미지 1 보장
    target['current_hp'] = max(0, target['current_hp'] - damage)
    
    battle.add_log(f"💥 {attacker['name']}이(가) {target['name']}에게 **{damage}**의 피해를 입혔습니다!")

    if target['current_hp'] == 0:
        await battle.end_battle(attacker, f"{target['name']}의 체력이 0이 되어 전투에서 승리했습니다!")
    else:
        await battle.handle_action_cost(1)


@bot.command(name="특수")
async def special_ability(ctx):
    battle = active_battles.get(ctx.channel.id)
    if not battle or ctx.author != battle.current_turn_player: return

    if battle.turn_actions_left < 2:
        return await ctx.send("특수 능력은 행동력을 소모하지 않은 상태에서만 사용할 수 있습니다.", delete_after=10)

    p_stats = battle.get_player_stats(ctx.author)
    if p_stats['special_cooldown'] > 0:
        return await ctx.send(f"쿨타임이 {p_stats['special_cooldown']}턴 남았습니다.", delete_after=10)

    # 직업별 특수 능력
    player_class = p_stats['class']
    if player_class == '마법사':
        empty_cells = [str(i+1) for i, cell in enumerate(battle.grid) if cell == "□"]
        await ctx.send(f"**텔레포트**: 이동할 위치의 번호를 입력해주세요. (1~15)\n> 가능한 위치: `{'`, `'.join(empty_cells)}`")
        def check(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit() and 1 <= int(m.content) <= 15
        try:
            msg = await bot.wait_for('message', check=check, timeout=30.0)
            target_pos = int(msg.content) - 1
            if battle.grid[target_pos] != "□":
                return await ctx.send("해당 위치는 비어있지 않습니다. 다시 시도해주세요.")
            
            battle.grid[p_stats['pos']] = "□"
            p_stats['pos'] = target_pos
            battle.grid[target_pos] = p_stats['emoji']
            battle.add_log(f"✨ {p_stats['name']}이(가) {target_pos+1}번 위치로 텔레포트했습니다!")

        except asyncio.TimeoutError: return await ctx.send("시간이 초과되어 취소되었습니다.")

    elif player_class == '마검사':
        heal_amount = p_stats['max_hp'] // 5
        p_stats['current_hp'] = min(p_stats['max_hp'], p_stats['current_hp'] + heal_amount)
        battle.add_log(f"💚 {p_stats['name']}이(가) 체력을 **{heal_amount}**만큼 회복했습니다!")

    elif player_class == '검사':
        self_damage = p_stats['level']
        p_stats['current_hp'] = max(1, p_stats['current_hp'] - self_damage)
        p_stats['double_damage_buff'] = True
        battle.add_log(f"🩸 {p_stats['name']}이(가) 자신의 체력을 소모하여 다음 공격을 강화합니다!")

    # 특수 능력 사용 후 처리
    p_stats['special_cooldown'] = 2 # 현재 턴 포함 2턴
    battle.turn_actions_left = 0
    await battle.display_board("특수 능력을 사용하여 턴을 종료합니다.")
    await asyncio.sleep(2)
    await battle.next_turn()

@bot.command(name="기권")
async def forfeit(ctx):
    battle = active_battles.get(ctx.channel.id)
    if not battle: return
    
    if ctx.author.id == battle.p1_user.id or ctx.author.id == battle.p2_user.id:
        winner_stats = battle.get_opponent_stats(ctx.author)
        await battle.end_battle(winner_stats, f"{ctx.author.display_name}님이 기권했습니다.")
    else:
        await ctx.send("당신은 이 전투의 참여자가 아닙니다.")

# --- 봇 실행 ---
if __name__ == "__main__":
        bot.run(DISCORD_TOKEN)
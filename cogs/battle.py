# cogs/battle.py

import discord
from discord.ext import commands
import json
import os
import random
import asyncio

DATA_FILE = "player_data.json"


# 데이터 로딩/저장 함수와 Battle/TeamBattle 클래스를 여기에 위치시킵니다.
def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

# --- 1:1 전투 관리 클래스 ---
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
        level = 1 + ((base_stats['mental'] + base_stats['physical']) // 5)
        max_hp = max(1, level * 10 + base_stats['physical'])
        if base_stats.get("rest_buff_active", False):
            hp_buff = level * 5
            max_hp += hp_buff
            self.add_log(f"🌙 {base_stats['name']}이(가) 휴식 효과로 최대 체력이 {hp_buff} 증가합니다!")
            all_data[player_id]["rest_buff_active"] = False
            save_data(all_data)
        return {
            "id": user.id, "name": base_stats['name'], "emoji": base_stats['emoji'], "class": base_stats['class'],
            "attribute": base_stats.get("attribute"), "advanced_class": base_stats.get("advanced_class"),
            "defense": 0, "effects": {},
            "color": int(base_stats['color'][1:], 16), "mental": base_stats['mental'], "physical": base_stats['physical'],
            "level": level, "max_hp": max_hp, "current_hp": max_hp,
            "pos": -1, "special_cooldown": 0, "double_damage_buff": 0
        }

    def get_player_stats(self, user): return self.p1_stats if user.id == self.p1_user.id else self.p2_stats
    def get_opponent_stats(self, user): return self.p2_stats if user.id == self.p1_user.id else self.p1_stats
    def add_log(self, message): 
        self.battle_log.append(message)
        if len(self.battle_log) > 5: 
            self.battle_log.pop(0)

    async def display_board(self, extra_message=""):
        turn_player_stats = self.get_player_stats(self.current_turn_player)
        embed = discord.Embed(title="⚔️ 1:1 대결 진행중 ⚔️", description=f"**현재 턴: {turn_player_stats['name']}**", color=turn_player_stats['color'])
        grid_str = ""
        for i, cell in enumerate(self.grid):
            grid_str += f" `{cell}` "
            if (i + 1) % 5 == 0: grid_str += "\n"
        embed.add_field(name="[ 전투 맵 ]", value=grid_str, inline=False)
        for p_stats in [self.p1_stats, self.p2_stats]:
            embed.add_field(name=f"{p_stats['emoji']} {p_stats['name']} ({p_stats['class']})", value=f"**HP: {p_stats['current_hp']} / {p_stats['max_hp']}**", inline=True)
        embed.add_field(name="남은 행동", value=f"{self.turn_actions_left}회", inline=False)
        embed.add_field(name="📜 전투 로그", value="\n".join(self.battle_log), inline=False)
        if extra_message: embed.set_footer(text=extra_message)
        await self.channel.send(embed=embed)

    async def handle_action_cost(self, cost=1):
        self.turn_actions_left -= cost
        if self.turn_actions_left <= 0:
            await self.display_board("행동력을 모두 소모하여 턴을 종료합니다."); await asyncio.sleep(2); await self.next_turn()
        else: await self.display_board()

    async def next_turn(self):
        # 현재 턴 플레이어의 효과 적용 및 초기화
        p_stats = self.get_player_stats(self.current_turn_player)
        if p_stats['special_cooldown'] > 0: p_stats['special_cooldown'] -= 1
        
        # 턴 전환
        self.current_turn_player = self.p2_user if self.current_turn_player.id == self.p1_user.id else self.p1_user
        self.turn_actions_left = 2

        # 새 턴 플레이어의 효과 적용
        next_p_stats = self.get_player_stats(self.current_turn_player)
        effects = next_p_stats.get('effects', {})
        if 'action_point_modifier' in effects:
            self.turn_actions_left += effects['action_point_modifier']
            self.add_log(f"⏱️ 효과로 인해 {next_p_stats['name']}의 행동 횟수가 조정됩니다!")
        next_p_stats['effects'] = {}

        self.add_log(f"▶️ {next_p_stats['name']}의 턴입니다.")
        await self.start_turn_timer()
        await self.display_board()

    async def start_turn_timer(self):
        if self.turn_timer: self.turn_timer.cancel()
        self.turn_timer = asyncio.create_task(self.timeout_task())

    async def timeout_task(self):
        try:
            await asyncio.sleep(300)
            winner = self.get_opponent_stats(self.current_turn_player)
            loser = self.get_player_stats(self.current_turn_player)
            await self.end_battle(winner, f"시간 초과로 {loser['name']}님이 패배했습니다.")
        except asyncio.CancelledError: pass

    async def end_battle(self, winner_user, reason):
        if self.turn_timer: self.turn_timer.cancel()
        winner_stats = self.get_player_stats(winner_user)
        embed = discord.Embed(title="🎉 전투 종료! 🎉", description=f"**승자: {winner_stats['name']}**\n> {reason}", color=winner_stats['color'])
        await self.channel.send(embed=embed)
        if self.channel.id in active_battles: del active_battles[self.channel.id]
        
    def get_coords(self, pos): return pos // 5, pos % 5
    def get_distance(self, pos1, pos2): r1, c1 = self.get_coords(pos1); r2, c2 = self.get_coords(pos2); return max(abs(r1 - r2), abs(c1 - c2))

# --- 팀 전투 관리 클래스 ---
class TeamBattle(Battle): # Battle 클래스의 기능을 상속받음
    def __init__(self, channel, team_a_users, team_b_users):
        self.channel = channel
        self.players = {}
        self.battle_log = ["팀 전투가 시작되었습니다!"]
        self.team_a_ids = [p.id for p in team_a_users]
        self.team_b_ids = [p.id for p in team_b_users]
        
        all_data = load_data()
        for player_user in team_a_users + team_b_users:
            self.players[player_user.id] = self._setup_player_stats(all_data, player_user)

        self.players[team_a_users[0].id]['pos'] = 0
        self.players[team_a_users[1].id]['pos'] = 10
        self.players[team_b_users[0].id]['pos'] = 4
        self.players[team_b_users[1].id]['pos'] = 14
        
        self.grid = ["□"] * 15
        for p_id, p_stats in self.players.items(): 
            self.grid[p_stats['pos']] = p_stats['emoji']

        if random.random() < 0.5:
            self.turn_order = [team_a_users[0].id, team_b_users[0].id, team_a_users[1].id, team_b_users[1].id]
            self.add_log("▶️ A팀이 선공입니다!")
        else:
            self.turn_order = [team_b_users[0].id, team_a_users[0].id, team_b_users[1].id, team_a_users[1].id]
            self.add_log("▶️ B팀이 선공입니다!")
        
        self.turn_index = -1
        self.current_turn_player_id = None
        self.turn_actions_left = 2
        self.turn_timer = None
    
    async def next_turn(self):
        self.turn_index = (self.turn_index + 1) % 4
        next_player_id = self.turn_order[self.turn_index]
        if self.players[next_player_id]['current_hp'] <= 0:
            self.add_log(f"↪️ {self.players[next_player_id]['name']}님은 리타이어하여 턴을 건너뜁니다.")
            await self.display_board(); await asyncio.sleep(1.5); await self.next_turn(); return

        self.current_turn_player_id = next_player_id
        self.turn_actions_left = 2
        current_player_stats = self.players[self.current_turn_player_id]

        effects = current_player_stats.get('effects', {})
        if 'action_point_modifier' in effects:
            self.turn_actions_left += effects['action_point_modifier']
            self.add_log(f"⏱️ 효과로 인해 {current_player_stats['name']}의 행동 횟수가 조정됩니다!")
        current_player_stats['effects'] = {}

        if current_player_stats['special_cooldown'] > 0: current_player_stats['special_cooldown'] -= 1
        self.add_log(f"▶️ {current_player_stats['name']}의 턴입니다.")
        await self.start_turn_timer(); await self.display_board()

    async def display_board(self, extra_message=""):
        turn_player_stats = self.players[self.current_turn_player_id]
        embed = discord.Embed(title="⚔️ 팀 대결 진행중 ⚔️", description=f"**현재 턴: {turn_player_stats['name']}**", color=turn_player_stats['color'])
        grid_str = ""
        for i, cell in enumerate(self.grid):
            grid_str += f" `{cell}` "
            if (i + 1) % 5 == 0: grid_str += "\n"
        embed.add_field(name="[ 전투 맵 ]", value=grid_str, inline=False)
        
        team_a_leader, team_a_member = self.players[self.team_a_ids[0]], self.players[self.team_a_ids[1]]
        team_b_leader, team_b_member = self.players[self.team_b_ids[0]], self.players[self.team_b_ids[1]]
        
        embed.add_field(name=f"A팀: {team_a_leader['name']} & {team_a_member['name']}", value=f"{team_a_leader['emoji']} HP: **{team_a_leader['current_hp']}/{team_a_leader['max_hp']}**\n{team_a_member['emoji']} HP: **{team_a_member['current_hp']}/{team_a_member['max_hp']}**", inline=True)
        embed.add_field(name=f"B팀: {team_b_leader['name']} & {team_b_member['name']}", value=f"{team_b_leader['emoji']} HP: **{team_b_leader['current_hp']}/{team_b_leader['max_hp']}**\n{team_b_member['emoji']} HP: **{team_b_member['current_hp']}/{team_b_member['max_hp']}**", inline=True)
        
        embed.add_field(name="남은 행동", value=f"{self.turn_actions_left}회", inline=False)
        embed.add_field(name="📜 전투 로그", value="\n".join(self.battle_log), inline=False)
        if extra_message: embed.set_footer(text=extra_message)
        await self.channel.send(embed=embed)

    async def check_game_over(self):
        team_a_alive = any(self.players[pid]['current_hp'] > 0 for pid in self.team_a_ids)
        team_b_alive = any(self.players[pid]['current_hp'] > 0 for pid in self.team_b_ids)
        if not team_a_alive: await self.end_battle("B팀", self.team_b_ids, "A팀이 전멸하여 B팀이 승리했습니다!"); return True
        if not team_b_alive: await self.end_battle("A팀", self.team_a_ids, "B팀이 전멸하여 A팀이 승리했습니다!"); return True
        return False
    
    async def end_battle(self, winner_team_name, winner_ids, reason):
        if self.turn_timer: self.turn_timer.cancel()
        winner_representative_stats = self.players[winner_ids[0]]
        embed = discord.Embed(title=f"🎉 {winner_team_name} 승리! 🎉", description=f"> {reason}", color=winner_representative_stats['color'])
        await self.channel.send(embed=embed)
        if self.channel.id in active_battles: del active_battles[self.channel.id]
    
    async def timeout_task(self):
        try:
            await asyncio.sleep(300)
            loser_player_id = self.current_turn_player_id
            if loser_player_id in self.team_a_ids: winner_team_name, winner_ids = "B팀", self.team_b_ids
            else: winner_team_name, winner_ids = "A팀", self.team_a_ids
            loser_name = self.players[loser_player_id]['name']
            await self.end_battle(winner_team_name, winner_ids, f"시간 초과로 {loser_name}님의 턴이 종료되어 상대팀이 승리했습니다.")
        except asyncio.CancelledError: pass

active_battles = {} # 전투 Cog가 활성 전투를 관리

# Cog 클래스 정의
class BattleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="대결")
    async def battle_request(self, ctx, opponent: discord.Member):
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
            reaction, user = await self.bot.wait_for('reaction_add', timeout=15.0, check=check)
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
            # ... !대결 명령어의 전체 코드를 여기에 붙여넣으세요 ...
            # Battle 객체를 생성할 때, 이 파일에 있는 active_battles를 사용합니다.

        
    @commands.command(name="팀대결")
    async def team_battle_request(self, ctx, teammate: discord.Member, opponent1: discord.Member, opponent2: discord.Member):
        if ctx.channel.id in active_battles: return await ctx.send("이 채널에서는 이미 전투가 진행중입니다.")
        players = {ctx.author, teammate, opponent1, opponent2}
        if len(players) < 4: return await ctx.send("모든 플레이어는 서로 다른 유저여야 합니다.")
        all_data = load_data()
        for p in players:
            if not all_data.get(str(p.id), {}).get("registered", False): return await ctx.send(f"{p.display_name}님은 아직 등록하지 않은 플레이어입니다.")

        msg = await ctx.send(f"**⚔️ 팀 대결 신청! ⚔️**\n\n**A팀**: {ctx.author.mention} (리더), {teammate.mention}\n**B팀**: {opponent1.mention} (리더), {opponent2.mention}\n\nB팀의 {opponent1.mention}, {opponent2.mention} 님! 대결을 수락하시면 30초 안에 ✅ 반응을 눌러주세요. (두 명 모두 수락해야 시작됩니다)")
        await msg.add_reaction("✅")
        accepted_opponents = set()
        def check(reaction, user): return str(reaction.emoji) == '✅' and user.id in [opponent1.id, opponent2.id]
        try:
            while len(accepted_opponents) < 2:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
                if user.id not in accepted_opponents:
                    accepted_opponents.add(user.id)
                    await ctx.send(f"✅ {user.display_name}님이 대결을 수락했습니다. (남은 인원: {2-len(accepted_opponents)}명)")
        except asyncio.TimeoutError: return await ctx.send("시간이 초과되어 대결이 취소되었습니다.")
        
        await ctx.send("양 팀 모두 대결을 수락했습니다! 전투를 시작합니다.")
        team_a = [ctx.author, teammate]; team_b = [opponent1, opponent2]
        battle = TeamBattle(ctx.channel, team_a, team_b)
        active_battles[ctx.channel.id] = battle
        await battle.next_turn()

    
    @commands.command(name="공격")
    async def attack(self, ctx, target_user: discord.Member = None):
        battle = active_battles.get(ctx.channel.id)
        if not battle: return
        
        # 1:1 대결과 팀 대결의 현재 턴 플레이어 확인 방식이 다름
        current_player_id = battle.current_turn_player.id if isinstance(battle, Battle) else battle.current_turn_player_id
        if ctx.author.id != current_player_id:
            return await ctx.send("자신의 턴이 아닙니다.", delete_after=5)

        if not target_user:
            return await ctx.send("공격할 대상을 `@멘션`으로 지정해주세요. (예: `!공격 @상대`)")

        # 팀 대결일 경우, 상대 팀원인지 확인하는 로직
        if isinstance(battle, TeamBattle):
            attacker_id = ctx.author.id
            target_id = target_user.id

            is_target_valid = False
            # 공격자가 A팀이고, 타겟이 B팀인 경우
            if attacker_id in battle.team_a_ids and target_id in battle.team_b_ids:
                is_target_valid = True
            # 공격자가 B팀이고, 타겟이 A팀인 경우
            elif attacker_id in battle.team_b_ids and target_id in battle.team_a_ids:
                is_target_valid = True
            
            if not is_target_valid:
                # 타겟이 같은 팀이거나, 전투 참여자가 아닌 경우
                return await ctx.send("❌ 같은 팀원이거나 유효하지 않은 대상은 공격할 수 없습니다.", delete_after=10)
        # ▲▲▲ 여기가 추가된 부분입니다 ▲▲▲


        if isinstance(battle, TeamBattle):
            attacker = battle.players[ctx.author.id]
            target = battle.players[target_user.id]
        else: # 1:1 대결
            attacker = battle.get_player_stats(ctx.author)
            target = battle.get_opponent_stats(ctx.author)

        # 거리 계산
        distance = battle.get_distance(attacker['pos'], target['pos'])
    

        can_attack, attack_type = False, ""
        # (공격 가능 여부 판정 로직은 동일)
        if attacker['class'] == '마법사' and 3 <= distance <= 5: can_attack, attack_type = True, "원거리"
        elif attacker['class'] == '마검사':
            if distance == 1: can_attack, attack_type = True, "근거리"
            elif 2 <= distance <= 3: can_attack, attack_type = True, "원거리"
        elif attacker['class'] == '검사' and distance == 1: can_attack, attack_type = True, "근거리"

        if not can_attack:
            return await ctx.send("❌ 공격 사거리가 아닙니다.", delete_after=10)
            
        # --- 데미지 계산 로직 (대폭 수정) ---

        # 1. 기본 데미지 계산
        base_damage = attacker['physical'] + random.randint(0, attacker['mental']) if attack_type == "근거리" else attacker['mental'] + random.randint(0, attacker['physical'])
        
        # 2. 크리티컬 및 각종 배율 계산
        multiplier = 1.0
        
        # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
        # 캐스터의 데미지 3배 버프를 최우선으로 확인
        attacker_effects = attacker.get('effects', {})
        if 'next_attack_multiplier' in attacker_effects:
            multiplier = attacker_effects['next_attack_multiplier']
            battle.add_log(f"✨ 영창 효과 발동! 데미지가 {multiplier}배 증폭됩니다!")
            # 사용한 효과는 즉시 제거
            del attacker['effects']['next_attack_multiplier']
        # ▲▲▲ 여기가 수정된 부분입니다 ▲▲▲

        # 검사 특수능력 버프 확인 (캐스터 버프가 없을 경우)
        elif attacker.get('double_damage_buff', 0) > 0:
            multiplier = 2.0
            attacker['double_damage_buff'] -= 1
            battle.add_log(f"🔥 {attacker['name']}의 분노의 일격! (남은 횟수: {attacker['double_damage_buff']}회)")
        # 10% 확률 크리티컬 발동 (위 버프들이 없을 경우)
        elif random.random() < 0.10: 
            multiplier = 2.0
            battle.add_log(f"💥 치명타 발생!")
        # 기본 직업 배율 (위 버프들이 없을 경우)
        else:
            if attacker['class'] == '마법사': multiplier = 1.5
            elif attacker['class'] == '검사': multiplier = 1.2
                
        # 3. 상성 데미지 계산
        advantages = {'Wit': 'Gut', 'Gut': 'Heart', 'Heart': 'Wit'}
        attribute_damage = 0
        if attacker['attribute'] and target['attribute']:
            # 유리한 상성일 경우
            if advantages.get(attacker['attribute']) == target['attribute']:
                bonus = random.randint(0, attacker['level'])
                attribute_damage += bonus
                battle.add_log(f"👍 상성 우위! 추가 데미지 +{bonus}")
            # 불리한 상성일 경우
            elif advantages.get(target['attribute']) == attacker['attribute']:
                penalty = random.randint(0, attacker['level'])
                attribute_damage -= penalty
                battle.add_log(f"👎 상성 열세... 데미지 감소 -{penalty}")

        # 4. 최종 데미지 계산
        total_damage = round(base_damage * multiplier) + attribute_damage
        final_damage = max(1, total_damage - target.get('defense', 0)) # 방어력 적용

        # --- 데미지 계산 로직 종료 ---

        target['current_hp'] = max(0, target['current_hp'] - final_damage)
        battle.add_log(f"💥 {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해를 입혔습니다!")

        if target['current_hp'] == 0:
            await battle.end_battle(attacker, f"{target['name']}의 체력이 0이 되어 전투에서 승리했습니다!")
        else:
            await battle.handle_action_cost(1)
        



     # --- 전투 행동 명령어 ---
    
    @commands.command(name="이동")
    async def move(self, ctx, *directions):
        battle = active_battles.get(ctx.channel.id)
        current_player_id = battle.current_turn_player.id if isinstance(battle, Battle) else battle.current_turn_player_id
        if not battle or ctx.author.id != current_player_id or battle.turn_actions_left <= 0:
            return # 아무 메시지 없이 조용히 종료하거나, delete_after로 메시지 전송

        p_stats = battle.get_player_stats(ctx.author)
        # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
        # 효과(effects)에 이동력 증감 버프가 있는지 확인
        effects = p_stats.get('effects', {})
        mobility_modifier = effects.get('mobility_modifier', 0)
        # ▲▲▲ 여기가 수정된 부분입니다 ▲▲▲

        # 기본 이동력에 버프/디버프 수치 적용
        base_mobility = 2 if p_stats['class'] == '검사' else 1
        final_mobility = max(1, base_mobility + mobility_modifier) # 최소 이동력은 1로 보정

        if not (1 <= len(directions) <= final_mobility):
            return await ctx.send(f"👉 현재 이동력은 **{final_mobility}**입니다. 1개에서 {final_mobility}개 사이의 방향을 입력해주세요.", delete_after=10)
        
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

    @commands.command(name="특수")
    async def special_ability(self, ctx):
        battle = active_battles.get(ctx.channel.id)
        if not battle: return

        # (공격 명령어와 마찬가지로 isinstance로 1:1과 팀전 구분하여 처리)
        # 특수는 자신에게만 사용하므로 대상 지정은 불필요
    
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
                msg = await self.bot.wait_for('message', check=check, timeout=30.0)
                target_pos = int(msg.content) - 1
                if battle.grid[target_pos] != "□":
                    return await ctx.send("해당 위치는 비어있지 않습니다. 다시 시도해주세요.")
                
                battle.grid[p_stats['pos']] = "□"
                p_stats['pos'] = target_pos
                battle.grid[target_pos] = p_stats['emoji']
                battle.add_log(f"✨ {p_stats['name']}이(가) {target_pos+1}번 위치로 텔레포트했습니다!")

            except asyncio.TimeoutError: return await ctx.send("시간이 초과되어 취소되었습니다.")

        
        # ▼▼▼ 마검사 특수 능력 효과 수정 ▼▼▼
        elif player_class == '마검사':
            heal_amount = p_stats['level'] # 자신의 레벨만큼 회복
            p_stats['current_hp'] = min(p_stats['max_hp'], p_stats['current_hp'] + heal_amount)
            battle.add_log(f"💚 {p_stats['name']}이(가) 체력을 **{heal_amount}**만큼 회복했습니다!")
        # ▲▲▲ 마검사 특수 능력 효과 수정 ▲▲▲

        # ▼▼▼ 검사 특수 능력 효과 수정 ▼▼▼
        elif player_class == '검사':
            self_damage = p_stats['level']
            p_stats['current_hp'] = max(1, p_stats['current_hp'] - self_damage)
            p_stats['double_damage_buff'] = 2  # 버프 횟수를 2로 설정
            battle.add_log(f"🩸 {p_stats['name']}이(가) 자신의 체력을 소모하여 다음 2회 공격을 강화합니다!")

        # ▼▼▼ 여기가 수정된 부분입니다 (행동력 1 소모로 변경) ▼▼▼
        p_stats['special_cooldown'] = 2 
        await battle.handle_action_cost(1) # 턴 전체 소모 대신 행동력 1 소모
        # ▲▲▲ 여기가 수정된 부분입니다 ▲▲▲ 


    @commands.command(name="스킬")
    async def use_skill(self, ctx, skill_number: int, target_user: discord.Member):
        battle = active_battles.get(ctx.channel.id)
        if not battle: return

        # 현재 턴 플레이어 확인 및 기본 조건 검사
        current_player_id = battle.current_turn_player_id if isinstance(battle, TeamBattle) else battle.current_turn_player.id
        if ctx.author.id != current_player_id:
            return await ctx.send("자신의 턴이 아닙니다.", delete_after=5)

        if battle.turn_actions_left <= 0:
            return await ctx.send("행동력이 없습니다.", delete_after=10)

        # 스탯 정보 가져오기
        attacker = battle.players[ctx.author.id] if isinstance(battle, TeamBattle) else battle.get_player_stats(ctx.author)
        
        if not attacker.get("advanced_class"):
            return await ctx.send("스킬은 상위 직업으로 전직한 플레이어만 사용할 수 있습니다.")
        
        if attacker['special_cooldown'] > 0:
            return await ctx.send(f"스킬/특수 능력의 쿨타임이 {attacker['special_cooldown']}턴 남았습니다.", delete_after=10)

        # 타겟 유효성 검사
        target_id = target_user.id
        if isinstance(battle, TeamBattle):
            target = battle.players.get(target_id)
        else: # 1:1 대결
            target = battle.get_player_stats(target_user) if target_id in [battle.p1_user.id, battle.p2_user.id] else None
        
        if not target:
            return await ctx.send("유효하지 않은 대상입니다.", delete_after=10)

        advanced_class = attacker['advanced_class']
        
        # --- 직업별 스킬 로직 구현 ---

        # [마법사 전직] -------------------------------------------
        if advanced_class == "캐스터":
            distance = battle.get_distance(attacker['pos'], target['pos'])
            if not (3 <= distance <= 5): return await ctx.send("❌ 원거리 공격 사거리가 아닙니다.", delete_after=10)
            
            if skill_number == 1: # 크리티컬 50% 원거리 공격
                base_damage = attacker['mental'] + random.randint(0, attacker['physical'])
                multiplier = 2.0 if random.random() < 0.5 else 1.5
                if multiplier == 2.0: battle.add_log(f"💥 캐스터의 주문이 치명타로 적중!")
                final_damage = max(1, round(base_damage * multiplier) - target.get('defense', 0))
                target['current_hp'] = max(0, target['current_hp'] - final_damage)
                battle.add_log(f"☄️ {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해를 입혔습니다!")

            elif skill_number == 2: # 대상 이동력 -1
                target.setdefault('effects', {})['mobility_modifier'] = -1
                battle.add_log(f"🌀 {attacker['name']}이(가) {target['name']}의 다음 턴 이동력을 1 감소시켰습니다!")

            elif skill_number == 3: # 3배 데미지 버프 (20% 확률)
                if random.random() < 0.20:
                    attacker.setdefault('effects', {})['next_attack_multiplier'] = 3.0
                    battle.add_log(f"✨ {attacker['name']}이(가) 주문 영창에 성공! 다음 공격 데미지가 3배가 됩니다!")
                else:
                    battle.add_log(f"💨 {attacker['name']}의 주문 영창이 실패했습니다...")
            else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)

        elif advanced_class == "힐러":
            if skill_number == 1: # 체력 40% 회복
                heal_amount = round(target['max_hp'] * 0.4)
                target['current_hp'] = min(target['max_hp'], target['current_hp'] + heal_amount)
                battle.add_log(f"💖 {attacker['name']}이(가) {target['name']}의 체력을 {heal_amount}만큼 회복시켰습니다!")

            elif skill_number == 2: # 대상 이동력 +1
                target.setdefault('effects', {})['mobility_modifier'] = 1
                battle.add_log(f"🍃 {attacker['name']}이(가) {target['name']}의 다음 턴 이동력을 1 증가시켰습니다!")
            else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)

        # [마검사 전직] -------------------------------------------
        elif advanced_class == "헌터":
            if skill_number == 1: # 크리티컬 50% 근거리 공격
                if battle.get_distance(attacker['pos'], target['pos']) != 1: return await ctx.send("❌ 근거리 공격 사거리가 아닙니다.", delete_after=10)
                base_damage = attacker['physical'] + random.randint(0, attacker['mental'])
                multiplier = 2.0 if random.random() < 0.5 else 1.0
                if multiplier == 2.0: battle.add_log(f"💥 헌터의 일격이 치명타로 적중!")
                final_damage = max(1, round(base_damage * multiplier) - target.get('defense', 0))
                target['current_hp'] = max(0, target['current_hp'] - final_damage)
                battle.add_log(f"🔪 {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해를 입혔습니다!")
                
            elif skill_number == 2: # 원거리 공격 + 방어 초기화
                if not (2 <= battle.get_distance(attacker['pos'], target['pos']) <= 3): return await ctx.send("❌ 원거리 공격 사거리가 아닙니다.", delete_after=10)
                base_damage = attacker['mental'] + random.randint(0, attacker['physical'])
                final_damage = max(1, round(base_damage) - target.get('defense', 0))
                target['current_hp'] = max(0, target['current_hp'] - final_damage)
                target['defense'] = 0
                battle.add_log(f"🏹 {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해를 입히고 방어도를 초기화했습니다!")
            else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)

        elif advanced_class == "조커":
            advantages = {'Wit': 'Gut', 'Gut': 'Heart', 'Heart': 'Wit'}
            if skill_number == 1: # 상성 우위 시 추가 데미지
                if not (2 <= battle.get_distance(attacker['pos'], target['pos']) <= 3): return await ctx.send("❌ 원거리 공격 사거리가 아닙니다.", delete_after=10)
                base_damage = attacker['mental'] + random.randint(0, attacker['physical'])
                bonus_damage = 0
                if advantages.get(attacker['attribute']) == target.get('attribute'):
                    bonus_damage = target['level'] * 2
                    battle.add_log(f"🃏 조커의 속임수! 상성 우위로 추가 데미지 +{bonus_damage}!")
                final_damage = max(1, round(base_damage) + bonus_damage - target.get('defense', 0))
                target['current_hp'] = max(0, target['current_hp'] - final_damage)
                battle.add_log(f"🎯 {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해를 입혔습니다!")

            elif skill_number == 2: # 상성 불리 시 자신에게 방어 부여
                if advantages.get(target.get('attribute')) == attacker.get('attribute'):
                    defense_gain = attacker['level'] * 2
                    attacker['defense'] += defense_gain
                    battle.add_log(f"🛡️ 조커가 상성 불리를 예측하고 자신에게 방어도 **{defense_gain}**을 부여합니다!")
                else:
                    battle.add_log(f"…{attacker['name']}이(가) 스킬을 사용했지만 아무 효과도 없었다.")
            else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)

        # [검사 전직] -------------------------------------------
        elif advanced_class == "워리어":
            if skill_number == 1: # 크리티컬 100% 근거리 공격
                if battle.get_distance(attacker['pos'], target['pos']) != 1: return await ctx.send("❌ 근거리 공격 사거리가 아닙니다.", delete_after=10)
                base_damage = attacker['physical'] + random.randint(0, attacker['mental'])
                multiplier = 2.0
                battle.add_log(f"‼️ 워리어의 필살의 일격!")
                final_damage = max(1, round(base_damage * multiplier) - target.get('defense', 0))
                target['current_hp'] = max(0, target['current_hp'] - final_damage)
                battle.add_log(f"⚔️ {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해를 입혔습니다!")

            elif skill_number == 2: # 대상 행동 횟수 감소
                target.setdefault('effects', {})['action_point_modifier'] = -1
                battle.add_log(f"⛓️ {attacker['name']}이(가) {target['name']}의 다음 턴 행동 횟수를 1회 감소시켰습니다!")
            else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)

        elif advanced_class == "디펜더":
            if skill_number == 1: # 대상에게 방어 부여
                defense_gain = attacker['level'] * 4
                target['defense'] += defense_gain
                battle.add_log(f"🛡️ {attacker['name']}이(가) {target['name']}에게 방어도 **{defense_gain}**을 부여합니다!")

            elif skill_number == 2: # 대상 행동 횟수 증가
                target.setdefault('effects', {})['action_point_modifier'] = 1
                battle.add_log(f"🏃 {attacker['name']}이(가) {target['name']}의 다음 턴 행동 횟수를 1회 증가시켜 총 3회가 되었습니다!")
            else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)


        # --- 스킬 사용 후 공통 처리 ---
        attacker['special_cooldown'] = 2 # 특수/스킬 쿨다운은 공유
        await battle.handle_action_cost(1) # 행동력 1 소모
        
        # 공격 스킬로 인해 게임이 끝났는지 확인
        if isinstance(battle, TeamBattle):
            await battle.check_game_over()
        elif target['current_hp'] <= 0: # 1:1 대결
            await battle.end_battle(attacker, f"{target['name']}의 체력이 0이 되어 전투에서 승리했습니다!")
        battle = active_battles.get(ctx.channel.id)
        if not battle: return

        # (isinstance로 1:1과 팀전 구분하여 처리)
        
        player_stats = battle.players.get(ctx.author.id) # 팀전 기준
        if not player_stats or not player_stats.get("advanced_class"):
            return await ctx.send("스킬은 상위 직업으로 전직한 플레이어만 사용할 수 있습니다.")


     
            
        # ... (다른 직업들의 스킬 로직도 위와 같은 방식으로 추가) ...

        # --- 스킬 사용 후 공통 처리 ---
        attacker['special_cooldown'] = 2
        await battle.handle_action_cost(1)

    @commands.command(name="기권")
    async def forfeit(self, ctx):
        battle = active_battles.get(ctx.channel.id)
        if not battle: return
        
        if ctx.author.id == battle.p1_user.id or ctx.author.id == battle.p2_user.id:
            winner_stats = battle.get_opponent_stats(ctx.author)
            await battle.end_battle(winner_stats, f"{ctx.author.display_name}님이 기권했습니다.")
        else:
            await ctx.send("당신은 이 전투의 참여자가 아닙니다.")


# 봇에 Cog를 추가하기 위한 필수 함수
async def setup(bot):
    await bot.add_cog(BattleCog(bot))
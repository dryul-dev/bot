# cogs/battle.py

import discord
from discord.ext import commands
import json
import os
import random
import asyncio
from cogs.monster import PveBattle

DATA_FILE = "player_data.json"

def load_data():
    if not os.path.exists("player_data.json"): return {}
    with open("player_data.json", 'r', encoding='utf-8') as f: return json.load(f)

def save_data(data):
    with open("player_data.json", 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)


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
        
        all_data = load_data()
        winner_id = str(winner_user.id)
        if winner_id in all_data:
            all_data[winner_id]['school_points'] = all_data[winner_id].get('school_points', 0) + 10
            save_data(all_data)
        
        embed = discord.Embed(title="🎉 전투 종료! 🎉", description=f"**승자: {winner_stats['name']}**\n> {reason}\n\n**획득: 10 스쿨 포인트**", color=winner_stats['color'])
        await self.channel.send(embed=embed)
        
    def get_coords(self, pos): return pos // 5, pos % 5
    def get_distance(self, pos1, pos2): r1, c1 = self.get_coords(pos1); r2, c2 = self.get_coords(pos2); return max(abs(r1 - r2), abs(c1 - c2))

# --- 팀 전투 관리 클래스 ---
class TeamBattle(Battle): # Battle 클래스의 기능을 상속받음
    def __init__(self, channel, team_a_users, team_b_users, bot):
        self.channel = channel
        self.bot = bot
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
        if self.turn_timer: 
            self.turn_timer.cancel()

        all_data = load_data()
        point_log = []
        for winner_id in winner_ids:
            winner_id_str = str(winner_id)
            if winner_id_str in all_data:
                all_data[winner_id_str]['school_points'] = all_data[winner_id_str].get('school_points', 0) + 15
                winner_name = self.players[winner_id]['name']
                point_log.append(f"{winner_name}: +15P")
        save_data(all_data)

        winner_representative_stats = self.players[winner_ids[0]]
        embed = discord.Embed(
            title=f"🎉 {winner_team_name} 승리! 🎉",
            description=f"> {reason}\n\n**획득: 15 스쿨 포인트**\n" + "\n".join(point_log),
            color=winner_representative_stats['color']
        )
        await self.channel.send(embed=embed)
    
    async def timeout_task(self):
        try:
            await asyncio.sleep(300)
            loser_player_id = self.current_turn_player_id
            if loser_player_id in self.team_a_ids: winner_team_name, winner_ids = "B팀", self.team_b_ids
            else: winner_team_name, winner_ids = "A팀", self.team_a_ids
            loser_name = self.players[loser_player_id]['name']
            await self.end_battle(winner_team_name, winner_ids, f"시간 초과로 {loser_name}님의 턴이 종료되어 상대팀이 승리했습니다.")
        except asyncio.CancelledError: pass



# Cog 클래스 정의
class BattleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_battles = bot.active_battles # main.py의 목록을 가져옴

    @commands.command(name="대결")
    async def battle_request(self, ctx, opponent: discord.Member):
        if ctx.author == opponent:
            await ctx.send("자기 자신과는 대결할 수 없습니다.")
            return
        if ctx.channel.id in self.active_battles:
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
                if str(reaction.emoji) == "✅":
                    await ctx.send("대결이 성사되었습니다! 전투를 시작합니다.")
                    battle = Battle(ctx.channel, ctx.author, opponent)
                    self.active_battles[ctx.channel.id] = battle
                    await battle.start_turn_timer()
                    await battle.display_board()
            else:
                await ctx.send("대결이 거절되었습니다.")
        except asyncio.TimeoutError:
            await ctx.send("시간이 초과되어 대결이 취소되었습니다.")

        
    @commands.command(name="팀대결")
    async def team_battle_request(self, ctx, teammate: discord.Member, opponent1: discord.Member, opponent2: discord.Member):
        if ctx.channel.id in self.active_battles: return await ctx.send("이 채널에서는 이미 전투가 진행중입니다.")
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
            await ctx.send("양 팀 모두 대결을 수락했습니다! 전투를 시작합니다.")
            team_a = [ctx.author, teammate]; team_b = [opponent1, opponent2]
            # 클래스에 active_battles 참조를 전달
            battle = TeamBattle(ctx.channel, team_a, team_b, self.active_battles)
            self.active_battles[ctx.channel.id] = battle
            await battle.next_turn()
        except asyncio.TimeoutError: return await ctx.send("시간이 초과되어 대결이 취소되었습니다.")
        
    async def get_current_player_and_battle(self, ctx):
        """모든 전투 명령어에서 공통으로 사용할 플레이어 및 전투 정보 확인 함수"""
        battle = self.active_battles.get(ctx.channel.id)
        if not battle: return None, None
        
        current_player_id = None
        if isinstance(battle, PveBattle):
            if battle.current_turn != "player": return None, None
            current_player_id = battle.player_stats['id']
        elif isinstance(battle, (Battle, TeamBattle)):
            current_player_id = battle.current_turn_player.id if isinstance(battle, Battle) else battle.current_turn_player_id

        if ctx.author.id != current_player_id: return None, None
        
        return battle, current_player_id        


    
    @commands.command(name="공격")
    async def attack(self, ctx, target_user: discord.Member = None):
        battle = self.active_battles.get(ctx.channel.id)
        if not battle: return
        
        # 1:1 대결과 팀 대결의 현재 턴 플레이어 확인 방식이 다름
        current_player_id = battle.current_turn_player.id if isinstance(battle, Battle) else battle.current_turn_player_id
        if ctx.author.id != current_player_id:
            return await ctx.send("자신의 턴이 아닙니다.", delete_after=5)

        # 1:1 대결의 경우 자동으로 상대방을 타겟으로 설정
        if isinstance(battle, Battle):
            if not target_user:
                target_user = battle.p2_user if ctx.author.id == battle.p1_user.id else battle.p1_user
            attacker = battle.get_player_stats(ctx.author)
            target = battle.get_player_stats(target_user)
        # 팀 대결의 경우 타겟을 명시해야 함
        elif isinstance(battle, TeamBattle):
            if not target_user:
                return await ctx.send("팀 대결에서는 공격할 대상을 `@멘션`으로 지정해주세요.")
            
            attacker_id = ctx.author.id
            target_id = target_user.id
            
            # 상대 팀원인지 확인
            is_target_valid = False
            if attacker_id in battle.team_a_ids and target_id in battle.team_b_ids:
                is_target_valid = True
            elif attacker_id in battle.team_b_ids and target_id in battle.team_a_ids:
                is_target_valid = True
            
            if not is_target_valid:
                return await ctx.send("❌ 같은 팀원이거나 유효하지 않은 대상은 공격할 수 없습니다.", delete_after=10)
            
            attacker = battle.players[ctx.author.id]
            target = battle.players[target_user.id]

        # 거리 계산
        distance = battle.get_distance(attacker['pos'], target['pos'])
        
        can_attack, attack_type = False, ""
        if attacker['class'] == '마법사' and 3 <= distance <= 5: 
            can_attack, attack_type = True, "원거리"
        elif attacker['class'] == '마검사':
            if distance == 1: can_attack, attack_type = True, "근거리"
            elif 2 <= distance <= 3: can_attack, attack_type = True, "원거리"
        elif attacker['class'] == '검사' and distance == 1: 
            can_attack, attack_type = True, "근거리"

        if not can_attack:
            return await ctx.send("❌ 공격 사거리가 아닙니다.", delete_after=10)
            
        # 데미지 계산
        base_damage = attacker['physical'] + random.randint(0, attacker['mental']) if attack_type == "근거리" else attacker['mental'] + random.randint(0, attacker['physical'])
        
        multiplier = 1.0
        
        # 캐스터의 데미지 3배 버프를 최우선으로 확인
        attacker_effects = attacker.get('effects', {})
        if 'next_attack_multiplier' in attacker_effects:
            multiplier = attacker_effects['next_attack_multiplier']
            battle.add_log(f"✨ 영창 효과 발동! 데미지가 {multiplier}배 증폭됩니다!")
            del attacker['effects']['next_attack_multiplier']
        # 검사 특수능력 버프 확인
        elif attacker.get('double_damage_buff', 0) > 0:
            multiplier = 2.0
            attacker['double_damage_buff'] -= 1
            battle.add_log(f"🔥 {attacker['name']}의 분노의 일격! (남은 횟수: {attacker['double_damage_buff']}회)")
        # 10% 확률 크리티컬 발동
        elif random.random() < 0.10: 
            multiplier = 2.0
            battle.add_log(f"💥 치명타 발생!")
        # 기본 직업 배율
        else:
            if attacker['class'] == '마법사': multiplier = 1.5
            elif attacker['class'] == '검사': multiplier = 1.2
                
        # 상성 데미지 계산
        advantages = {'Wit': 'Gut', 'Gut': 'Heart', 'Heart': 'Wit'}
        attribute_damage = 0
        if attacker.get('attribute') and target.get('attribute'):
            if advantages.get(attacker['attribute']) == target['attribute']:
                bonus = random.randint(0, attacker['level'])
                attribute_damage += bonus
                battle.add_log(f"👍 상성 우위! 추가 데미지 +{bonus}")
            elif advantages.get(target['attribute']) == attacker['attribute']:
                penalty = random.randint(0, attacker['level'])
                attribute_damage -= penalty
                battle.add_log(f"👎 상성 열세... 데미지 감소 -{penalty}")

        # 최종 데미지 계산
        total_damage = round(base_damage * multiplier) + attribute_damage
        final_damage = max(1, total_damage - target.get('defense', 0))

        target['current_hp'] = max(0, target['current_hp'] - final_damage)
        battle.add_log(f"💥 {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해를 입혔습니다!")

        # 공격 후 체력이 0이 되어 전투가 끝났을 때
        # 공격 후 체력이 0이 되어 전투가 끝났을 때
        if target['current_hp'] <= 0:
            # 팀 대결일 경우, 팀 전체가 전멸했는지 확인
            if isinstance(battle, TeamBattle):
                # check_game_over가 end_battle을 호출하고 전투 목록에서 제거
                await battle.check_game_over()
            
            # 1:1 대결일 경우
            elif isinstance(battle, Battle):
                # 승리 처리 후 전투 목록에서 제거
                await battle.end_battle(ctx.author, f"{target['name']}의 체력이 0이 되어 전투에서 승리했습니다!")
                if ctx.channel.id in self.active_battles:
                    del self.active_battles[ctx.channel.id]
            
            # PvE 사냥일 경우
            elif isinstance(battle, PveBattle):
                # 승리 처리 (end_battle 내부에서 목록 제거)
                await battle.end_battle(win=True)

        # 전투가 계속될 경우
        else:
            if isinstance(battle, PveBattle):
                # 몬스터 턴 진행
                await battle.monster_turn()
            else:
                # PvP 턴 넘기기
                await battle.handle_action_cost(1)

            
    @commands.command(name="이동")
    async def move(self, ctx, *directions):
        battle, current_player_id = await self.get_current_player_and_battle(ctx)
        if not battle: return

        if isinstance(battle, PveBattle):
            return await ctx.send("사냥 중에는 이동할 수 없습니다.")
        
        current_player_id = battle.current_turn_player.id if isinstance(battle, Battle) else battle.current_turn_player_id
        if ctx.author.id != current_player_id or battle.turn_actions_left <= 0:
            return

        if isinstance(battle, Battle):
            p_stats = battle.get_player_stats(ctx.author)
            opponent_pos = battle.get_opponent_stats(ctx.author)['pos']
        else:  # TeamBattle
            p_stats = battle.players[ctx.author.id]
            # 팀전에서는 모든 다른 플레이어 위치 확인
            occupied_positions = [battle.players[pid]['pos'] for pid in battle.players if pid != ctx.author.id]

        # 이동력 계산
        effects = p_stats.get('effects', {})
        mobility_modifier = effects.get('mobility_modifier', 0)
        base_mobility = 2 if p_stats['class'] == '검사' else 1
        final_mobility = max(1, base_mobility + mobility_modifier)

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
        
        # 다른 플레이어와 겹치는지 확인
        if isinstance(battle, Battle):
            if final_pos == opponent_pos:
                return await ctx.send("❌ 상대방이 있는 칸으로 이동할 수 없습니다.", delete_after=10)
        else:  # TeamBattle
            if final_pos in occupied_positions:
                return await ctx.send("❌ 다른 플레이어가 있는 칸으로 이동할 수 없습니다.", delete_after=10)
        
        # 상태 업데이트
        battle.grid[current_pos] = "□"
        battle.grid[final_pos] = p_stats['emoji']
        p_stats['pos'] = final_pos
        battle.add_log(f"🚶 {p_stats['name']}이(가) 이동했습니다.")
        await battle.handle_action_cost(1)

    @commands.command(name="특수")
    async def special_ability(self, ctx):
        battle, current_player_id = await self.get_current_player_and_battle(ctx)
        if not battle: return

        current_player_id = battle.current_turn_player.id if isinstance(battle, Battle) else battle.current_turn_player_id
        if ctx.author.id != current_player_id:
            return await ctx.send("자신의 턴이 아닙니다.", delete_after=5)

        if isinstance(battle, Battle):
            p_stats = battle.get_player_stats(ctx.author)
        else:  # TeamBattle
            p_stats = battle.players[ctx.author.id]
            
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

            except asyncio.TimeoutError: 
                return await ctx.send("시간이 초과되어 취소되었습니다.")

        elif player_class == '마검사':
            heal_amount = p_stats['level']
            p_stats['current_hp'] = min(p_stats['max_hp'], p_stats['current_hp'] + heal_amount)
            battle.add_log(f"💚 {p_stats['name']}이(가) 체력을 **{heal_amount}**만큼 회복했습니다!")

        elif player_class == '검사':
            self_damage = p_stats['level']
            p_stats['current_hp'] = max(1, p_stats['current_hp'] - self_damage)
            p_stats['double_damage_buff'] = 2
            battle.add_log(f"🩸 {p_stats['name']}이(가) 자신의 체력을 소모하여 다음 2회 공격을 강화합니다!")

        p_stats['special_cooldown'] = 2 
        await battle.handle_action_cost(1)



    @commands.command(name="스킬")
    async def use_skill(self, ctx, skill_number: int, target_user: discord.Member = None):
        battle, current_player_id = await self.get_current_player_and_battle(ctx)
        if not battle: return

        # --- 1. 현재 턴 플레이어 및 기본 정보 확인 ---
        attacker = None
        if isinstance(battle, PveBattle):
            if battle.current_turn != "player": return await ctx.send("플레이어의 턴이 아닙니다.", delete_after=5)
            attacker = battle.player_stats
        elif isinstance(battle, (Battle, TeamBattle)):
            current_player_id = battle.current_turn_player.id if isinstance(battle, Battle) else battle.current_turn_player_id
            if ctx.author.id != current_player_id: return await ctx.send("자신의 턴이 아닙니다.", delete_after=5)
            if battle.turn_actions_left <= 0: return await ctx.send("행동력이 없습니다.", delete_after=10)
            attacker = battle.players[ctx.author.id] if isinstance(battle, TeamBattle) else battle.get_player_stats(ctx.author)
        
        if not attacker.get("advanced_class"):
            return await ctx.send("스킬은 상위 직업으로 전직한 플레이어만 사용할 수 있습니다.")
        if attacker.get('special_cooldown', 0) > 0:
            return await ctx.send(f"스킬/특수 능력의 쿨타임이 {attacker['special_cooldown']}턴 남았습니다.", delete_after=10)

        advanced_class = attacker['advanced_class']

        # --- 2. 전투 상황에 따라 로직 분기 ---

        # [ PvE (몬스터 사냥) 로직 ]
        if isinstance(battle, PveBattle):
            if skill_number != 1:
                return await ctx.send("사냥 중에는 1번 스킬만 사용할 수 있습니다.")

            # 힐러/디펜더는 자신에게, 나머지는 몬스터를 타겟으로 자동 설정
            target = attacker if advanced_class in ['힐러', '디펜더'] else battle.monster_stats
            
            # --- PvE 전용 1번 스킬 효과 적용 ---
            if advanced_class == "캐스터":
                base_damage = attacker['mental'] + random.randint(0, attacker['physical'])
                multiplier = 2.0 if random.random() < 0.5 else 1.5
                final_damage = max(1, round(base_damage * multiplier))
                target['current_hp'] = max(0, target['current_hp'] - final_damage)
                battle.add_log(f"☄️ {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해!")
            
            elif advanced_class == "힐러":
                heal_amount = round(attacker['hp'] * 0.4)
                attacker['current_hp'] = min(attacker['hp'], attacker['current_hp'] + heal_amount)
                battle.add_log(f"💖 {attacker['name']}이(가) 자신의 체력을 {heal_amount}만큼 회복!")

            elif advanced_class == "헌터":
                base_damage = attacker['physical'] + random.randint(0, attacker['mental'])
                multiplier = 2.0 if random.random() < 0.5 else 1.0
                final_damage = max(1, round(base_damage * multiplier))
                target['current_hp'] = max(0, target['current_hp'] - final_damage)
                battle.add_log(f"🔪 {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해!")
                
            elif advanced_class == "조커":
                base_damage = attacker['mental'] + random.randint(0, attacker['physical'])
                bonus_damage = 0
                if target['attribute'] == 'Gut': # 조커(Wit) > 몬스터(Gut)
                    bonus_damage = target['level'] * 2
                    battle.add_log(f"🃏 조커의 속임수! 상성 우위로 추가 데미지 +{bonus_damage}!")
                final_damage = max(1, round(base_damage) + bonus_damage)
                target['current_hp'] = max(0, target['current_hp'] - final_damage)
                battle.add_log(f"🎯 {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해!")
            
            elif advanced_class == "워리어":
                base_damage = attacker['physical'] + random.randint(0, attacker['mental'])
                final_damage = max(1, round(base_damage * 2.0))
                target['current_hp'] = max(0, target['current_hp'] - final_damage)
                battle.add_log(f"⚔️ {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 필살 피해!")
                
            elif advanced_class == "디펜더":
                defense_gain = attacker['level'] * 4
                attacker['pve_defense'] = attacker.get('pve_defense', 0) + defense_gain # PvE 전용 방어력
                battle.add_log(f"🛡️ {attacker['name']}이(가) 자신에게 방어도 **{defense_gain}**을 부여합니다!")
            
            attacker['special_cooldown'] = 2
            
            if battle.monster_stats['current_hp'] <= 0:
                await battle.end_battle(win=True)
            else:
                await battle.monster_turn()
            return

        # [ PvP (1:1, 팀 대결) 로직 ]
        elif isinstance(battle, (Battle, TeamBattle)):
            if not target_user:
                return await ctx.send("PvP에서는 스킬 대상을 `@멘션`으로 지정해야 합니다.")
            
            target_id = target_user.id
            target = battle.players.get(target_id) if isinstance(battle, TeamBattle) else (battle.get_player_stats(target_user) if target_id in [battle.p1_user.id, battle.p2_user.id] else None)
            if not target: return await ctx.send("유효하지 않은 대상입니다.", delete_after=10)

            # --- PvP 전용 스킬 로직 ---
            if advanced_class == "캐스터":
                distance = battle.get_distance(attacker['pos'], target['pos'])
                if not (3 <= distance <= 5): return await ctx.send("❌ 원거리 공격 사거리가 아닙니다.", delete_after=10)
                if skill_number == 1:
                    base_damage = attacker['mental'] + random.randint(0, attacker['physical']); multiplier = 2.0 if random.random() < 0.5 else 1.5
                    if multiplier == 2.0: battle.add_log(f"💥 캐스터의 주문이 치명타로 적중!")
                    final_damage = max(1, round(base_damage * multiplier) - target.get('defense', 0)); target['current_hp'] = max(0, target['current_hp'] - final_damage)
                    battle.add_log(f"☄️ {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해!")
                elif skill_number == 2: target.setdefault('effects', {})['mobility_modifier'] = -1; battle.add_log(f"🌀 {attacker['name']}이(가) {target['name']}의 다음 턴 이동력을 1 감소!")
                elif skill_number == 3:
                    if random.random() < 0.20: attacker.setdefault('effects', {})['next_attack_multiplier'] = 3.0; battle.add_log(f"✨ {attacker['name']} 주문 영창 성공! 다음 공격 3배!")
                    else: battle.add_log(f"💨 {attacker['name']}의 주문 영창이 실패했다...")
                else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)
            
            elif advanced_class == "힐러":
                if skill_number == 1: heal_amount = round(target['max_hp'] * 0.4); target['current_hp'] = min(target['max_hp'], target['current_hp'] + heal_amount); battle.add_log(f"💖 {attacker['name']}이(가) {target['name']}의 체력을 {heal_amount}만큼 회복!")
                elif skill_number == 2: target.setdefault('effects', {})['mobility_modifier'] = 1; battle.add_log(f"🍃 {attacker['name']}이(가) {target['name']}의 다음 턴 이동력을 1 증가!")
                else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)
            
            elif advanced_class == "헌터":
                if skill_number == 1:
                    if battle.get_distance(attacker['pos'], target['pos']) != 1: return await ctx.send("❌ 근거리 공격 사거리가 아닙니다.", delete_after=10)
                    base_damage = attacker['physical'] + random.randint(0, attacker['mental']); multiplier = 2.0 if random.random() < 0.5 else 1.0
                    if multiplier == 2.0: battle.add_log(f"💥 헌터의 일격이 치명타로 적중!")
                    final_damage = max(1, round(base_damage * multiplier) - target.get('defense', 0)); target['current_hp'] = max(0, target['current_hp'] - final_damage)
                    battle.add_log(f"🔪 {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해!")
                elif skill_number == 2:
                    if not (2 <= battle.get_distance(attacker['pos'], target['pos']) <= 3): return await ctx.send("❌ 원거리 공격 사거리가 아닙니다.", delete_after=10)
                    base_damage = attacker['mental'] + random.randint(0, attacker['physical'])
                    final_damage = max(1, round(base_damage) - target.get('defense', 0)); target['current_hp'] = max(0, target['current_hp'] - final_damage); target['defense'] = 0
                    battle.add_log(f"🏹 {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해를 입히고 방어도를 초기화!")
                else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)

            elif advanced_class == "조커":
                advantages = {'Wit': 'Gut', 'Gut': 'Heart', 'Heart': 'Wit'}
                if skill_number == 1:
                    if not (2 <= battle.get_distance(attacker['pos'], target['pos']) <= 3): return await ctx.send("❌ 원거리 공격 사거리가 아닙니다.", delete_after=10)
                    base_damage = attacker['mental'] + random.randint(0, attacker['physical']); bonus_damage = 0
                    if advantages.get(attacker['attribute']) == target.get('attribute'): bonus_damage = target['level'] * 2; battle.add_log(f"🃏 상성 우위! 추가 데미지 +{bonus_damage}!")
                    final_damage = max(1, round(base_damage) + bonus_damage - target.get('defense', 0)); target['current_hp'] = max(0, target['current_hp'] - final_damage)
                    battle.add_log(f"🎯 {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해!")
                elif skill_number == 2:
                    if advantages.get(target.get('attribute')) == attacker.get('attribute'): defense_gain = attacker['level'] * 2; attacker['defense'] += defense_gain; battle.add_log(f"🛡️ 상성 불리 예측! 자신에게 방어도 **{defense_gain}** 부여!")
                    else: battle.add_log(f"…{attacker['name']}이(가) 스킬을 사용했지만 아무 효과도 없었다.")
                else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)
            
            elif advanced_class == "워리어":
                if skill_number == 1:
                    if battle.get_distance(attacker['pos'], target['pos']) != 1: return await ctx.send("❌ 근거리 공격 사거리가 아닙니다.", delete_after=10)
                    base_damage = attacker['physical'] + random.randint(0, attacker['mental'])
                    final_damage = max(1, round(base_damage * 2.0) - target.get('defense', 0)); target['current_hp'] = max(0, target['current_hp'] - final_damage)
                    battle.add_log(f"⚔️ {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 필살 피해!")
                elif skill_number == 2: target.setdefault('effects', {})['action_point_modifier'] = -1; battle.add_log(f"⛓️ {attacker['name']}이(가) {target['name']}의 다음 턴 행동 횟수를 1회 감소!")
                else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)

            elif advanced_class == "디펜더":
                if skill_number == 1: defense_gain = attacker['level'] * 4; target['defense'] += defense_gain; battle.add_log(f"🛡️ {attacker['name']}이(가) {target['name']}에게 방어도 **{defense_gain}** 부여!")
                elif skill_number == 2: target.setdefault('effects', {})['action_point_modifier'] = 1; battle.add_log(f"🏃 {attacker['name']}이(가) {target['name']}의 다음 턴 행동 횟수를 1회 증가!")
                else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)

            # --- PvP 스킬 사용 후 공통 처리 ---
            attacker['special_cooldown'] = 2
            await battle.handle_action_cost(1)
            
            if isinstance(battle, TeamBattle):
                await battle.check_game_over()
            elif target['current_hp'] <= 0:
                await battle.end_battle(ctx.author, f"{target['name']}이(가) 스킬에 맞아 쓰러졌습니다!")
            return


    @commands.command(name="기권")
    async def forfeit(self, ctx):
        battle= await self.get_current_player_and_battle(ctx)
        if not battle: return
        
        if isinstance(battle, Battle):
            if ctx.author.id == battle.p1_user.id or ctx.author.id == battle.p2_user.id:
                winner_user = battle.p2_user if ctx.author.id == battle.p1_user.id else battle.p1_user
                await battle.end_battle(winner_user, f"{ctx.author.display_name}님이 기권했습니다.")
            else:
                await ctx.send("당신은 이 전투의 참여자가 아닙니다.")
        elif isinstance(battle, TeamBattle):
            if ctx.author.id in battle.team_a_ids:
                await battle.end_battle("B팀", battle.team_b_ids, f"A팀의 {ctx.author.display_name}님이 기권했습니다.")
            elif ctx.author.id in battle.team_b_ids:
                await battle.end_battle("A팀", battle.team_a_ids, f"B팀의 {ctx.author.display_name}님이 기권했습니다.")
            else:
                await ctx.send("당신은 이 전투의 참여자가 아닙니다.")

        if ctx.channel.id in self.active_battles:
            del self.active_battles[ctx.channel.id]


# 봇에 Cog를 추가하기 위한 필수 함수
async def setup(bot):
    await bot.add_cog(BattleCog(bot))

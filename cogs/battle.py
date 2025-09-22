import discord
from discord.ext import commands
import json
import os
import random
import asyncio

# --- 데이터 관리 함수 ---
DATA_FILE = "player_data.json"
def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)
def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

# --- 전투 관리 클래스 ---
class Battle:
    def __init__(self, channel, player1, player2, active_battles_ref):
        self.channel = channel
        self.active_battles = active_battles_ref
        self.p1_user = player1
        self.p2_user = player2
        self.battle_type = "pvp_1v1"
        self.grid = ["□"] * 15
        self.turn_timer = None
        self.battle_log = ["전투가 시작되었습니다!"]
        all_data = load_data()
        self.p1_stats = self._setup_player_stats(all_data, self.p1_user)
        self.p2_stats = self._setup_player_stats(all_data, self.p2_user)
        positions = random.sample([0, 14], 2)
        self.p1_stats['pos'] = positions[0]; self.p2_stats['pos'] = positions[1]
        self.grid[self.p1_stats['pos']] = self.p1_stats['emoji']
        self.grid[self.p2_stats['pos']] = self.p2_stats['emoji']
        self.current_turn_player = random.choice([self.p1_user, self.p2_user])
        self.turn_actions_left = 2

    def _setup_player_stats(self, all_data, user):
        player_data = all_data[str(user.id)]
        level = 1 + ((player_data.get('mental', 0) + player_data.get('physical', 0)) // 5)
        max_hp = max(1, level * 10 + player_data.get('physical', 0))
        return {"id": user.id, "name": player_data['name'], "emoji": player_data['emoji'], "class": player_data['class'], "defense": 0, "color": int(player_data.get('color', '#FFFFFF')[1:], 16), "mental": player_data.get('mental', 0), "physical": player_data.get('physical', 0), "level": level, "max_hp": max_hp, "current_hp": max_hp, "pos": -1, "special_cooldown": 0, "attack_buff_stacks": 0}

    def get_player_stats(self, user): return self.p1_stats if user.id == self.p1_user.id else self.p2_stats
    def get_opponent_stats(self, user): return self.p2_stats if user.id == self.p1_user.id else self.p1_stats
    def add_log(self, message):
        self.battle_log.append(message)
        if len(self.battle_log) > 5:
            self.battle_log.pop(0)
    def get_coords(self, pos): return pos // 5, pos % 5
    def get_distance(self, pos1, pos2): r1, c1 = self.get_coords(pos1); r2, c2 = self.get_coords(pos2); return abs(r1 - r2) + abs(c1 - c2)
    
    async def display_board(self, extra_message=""):
        turn_player_stats = self.get_player_stats(self.current_turn_player)
        embed = discord.Embed(title="⚔️ 1:1 대결 진행중 ⚔️", description=f"**현재 턴: {turn_player_stats['name']}**", color=turn_player_stats['color'])
        grid_str = "".join([f" `{cell}` " + ("\n" if (i + 1) % 5 == 0 else "") for i, cell in enumerate(self.grid)])
        embed.add_field(name="[ 전투 맵 ]", value=grid_str, inline=False)
        for p_stats in [self.p1_stats, self.p2_stats]:
            embed.add_field(name=f"{p_stats['emoji']} {p_stats['name']} ({p_stats['class']})", value=f"**HP: {p_stats['current_hp']} / {p_stats['max_hp']}**", inline=True)
        embed.add_field(name="남은 행동", value=f"{self.turn_actions_left}회", inline=False)
        embed.add_field(name="📜 전투 로그", value="\n".join(self.battle_log), inline=False)
        if extra_message: embed.set_footer(text=extra_message)
        await self.channel.send(embed=embed)

    async def handle_action_cost(self, cost=1):
        self.turn_actions_left -= cost
        if self.turn_actions_left <= 0: await self.display_board("행동력을 모두 소모하여 턴을 종료합니다."); await asyncio.sleep(2); await self.next_turn()
        else: await self.display_board()

# cogs/battle.py 의 Battle 클래스 내부

    async def next_turn(self):
        # 현재 턴 플레이어의 쿨다운 처리
        p_stats = self.get_player_stats(self.current_turn_player)
        if p_stats.get('special_cooldown', 0) > 0:
            p_stats['special_cooldown'] -= 1
        
        # 턴 전환
        self.current_turn_player = self.p2_user if self.current_turn_player.id == self.p1_user.id else self.p1_user
        self.turn_actions_left = 2
        
        # 새 턴 알림
        next_p_stats = self.get_player_stats(self.current_turn_player)
        self.add_log(f"▶️ {next_p_stats['name']}의 턴입니다.")
        await self.start_turn_timer()
        await self.display_board()
    
    async def start_turn_timer(self):
        if self.turn_timer: self.turn_timer.cancel()
        self.turn_timer = asyncio.create_task(self.timeout_task())
    async def timeout_task(self):
        try:
            await asyncio.sleep(300); loser = self.current_turn_player; winner = self.get_opponent_stats(loser)
            await self.end_battle(winner, f"시간 초과로 {loser.display_name}님이 패배했습니다.")
            if self.channel.id in self.active_battles: del self.active_battles[self.channel.id]
        except asyncio.CancelledError: pass

    async def end_battle(self, winner_user, reason):
        if self.turn_timer: self.turn_timer.cancel()
        winner_stats = self.get_player_stats(winner_user)
        embed = discord.Embed(title="🎉 전투 종료! 🎉", description=f"**승자: {winner_stats['name']}**\n> {reason}", color=winner_stats['color'])
        await self.channel.send(embed=embed)

# --- 팀 전투 관리 클래스 (최종본) ---
class TeamBattle(Battle):
    def __init__(self, channel, team_a_users, team_b_users, active_battles_ref):
        self.channel = channel
        self.active_battles = active_battles_ref
        self.players = {} # {id: stats}
        self.battle_log = ["팀 전투가 시작되었습니다!"]
        self.battle_type = "pvp_team"
        
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
    
# cogs/battle.py 의 TeamBattle 클래스 내부

    async def next_turn(self):
        # 현재 턴 플레이어의 쿨다운 처리
        if self.current_turn_player_id:
            p_stats = self.players[self.current_turn_player_id]
            if p_stats.get('special_cooldown', 0) > 0:
                p_stats['special_cooldown'] -= 1

        # 리타이어하지 않은 다음 플레이어를 찾음
        for _ in range(4): # 최대 4번 반복하여 다음 턴 주자를 찾음
            self.turn_index = (self.turn_index + 1) % 4
            next_player_id = self.turn_order[self.turn_index]
            
            if self.players[next_player_id]['current_hp'] > 0:
                # 유효한 플레이어를 찾았으면 턴 시작
                self.current_turn_player_id = next_player_id
                self.turn_actions_left = 2
                
                next_p_stats = self.players[next_player_id]
                self.add_log(f"▶️ {next_p_stats['name']}의 턴입니다.")
                await self.start_turn_timer()
                await self.display_board()
                return # 함수 종료
            
        self.add_log(f"▶️ {next_p_stats['name']}의 턴입니다.")
        await self.start_turn_timer()
        await self.display_board()

    async def display_board(self, extra_message=""):
        turn_player_stats = self.players[self.current_turn_player_id]
        embed = discord.Embed(title="⚔️ 팀 대결 진행중 ⚔️", description=f"**현재 턴: {turn_player_stats['name']}**", color=turn_player_stats['color'])
        grid_str = "".join([f" `{cell}` " + ("\n" if (i + 1) % 5 == 0 else "") for i, cell in enumerate(self.grid)])
        embed.add_field(name="[ 전투 맵 ]", value=grid_str, inline=False)
        
        team_a_leader, team_a_member = self.players[self.team_a_ids[0]], self.players[self.team_a_ids[1]]
        team_b_leader, team_b_member = self.players[self.team_b_ids[0]], self.players[self.team_b_ids[1]]
        
        adv_class_a1 = team_a_leader.get('advanced_class') or team_a_leader['class']
        adv_class_a2 = team_a_member.get('advanced_class') or team_a_member['class']
        adv_class_b1 = team_b_leader.get('advanced_class') or team_b_leader['class']
        adv_class_b2 = team_b_member.get('advanced_class') or team_b_member['class']

        embed.add_field(name=f"A팀: {team_a_leader['name']}({adv_class_a1}) & {team_a_member['name']}({adv_class_a2})", 
                        value=f"{team_a_leader['emoji']} HP: **{team_a_leader['current_hp']}/{team_a_leader['max_hp']}**\n{team_a_member['emoji']} HP: **{team_a_member['current_hp']}/{team_a_member['max_hp']}**", 
                        inline=True)
        embed.add_field(name=f"B팀: {team_b_leader['name']}({adv_class_b1}) & {team_b_member['name']}({adv_class_b2})", 
                        value=f"{team_b_leader['emoji']} HP: **{team_b_leader['current_hp']}/{team_b_leader['max_hp']}**\n{team_b_member['emoji']} HP: **{team_b_member['current_hp']}/{team_b_member['max_hp']}**", 
                        inline=True)
        
        embed.add_field(name="남은 행동", value=f"{self.turn_actions_left}회", inline=False)
        embed.add_field(name="📜 전투 로그", value="\n".join(self.battle_log), inline=False)
        if extra_message: embed.set_footer(text=extra_message)
        await self.channel.send(embed=embed)


    def handle_retirement(self, retired_player_stats):
        """리타이어한 플레이어를 맵에서 제거하고 로그를 추가합니다."""
        pos = retired_player_stats.get('pos')
        if pos is not None and self.grid[pos] == retired_player_stats.get('emoji'):
            self.grid[pos] = "□" # 맵에서 아이콘을 빈칸으로 변경
        self.add_log(f"☠️ {retired_player_stats['name']}이(가) 쓰러졌습니다!")



    async def check_game_over(self):
        team_a_alive = any(self.players[pid]['current_hp'] > 0 for pid in self.team_a_ids)
        team_b_alive = any(self.players[pid]['current_hp'] > 0 for pid in self.team_b_ids)
        if not team_a_alive:
            await self.end_battle("B팀", self.team_b_ids, "A팀이 전멸하여 B팀이 승리했습니다!")
            return True
        if not team_b_alive:
            await self.end_battle("A팀", self.team_a_ids, "B팀이 전멸하여 A팀이 승리했습니다!")
            return True
        return False
    
    async def end_battle(self, winner_team_name, winner_ids, reason):
        if self.turn_timer: self.turn_timer.cancel()
        all_data = load_data(); point_log = []
        for winner_id in winner_ids:
            winner_id_str = str(winner_id)
            if winner_id_str in all_data:
                all_data[winner_id_str]['school_points'] = all_data[winner_id_str].get('school_points', 0) + 15
                winner_name = self.players[winner_id]['name']; point_log.append(f"{winner_name}: +20P")
        save_data(all_data)
        winner_representative_stats = self.players[winner_ids[0]]
        embed = discord.Embed(title=f"🎉 {winner_team_name} 승리! 🎉", description=f"> {reason}\n\n**획득: 20 스쿨 포인트**\n" + "\n".join(point_log), color=winner_representative_stats['color'])
        await self.channel.send(embed=embed)

#============================================================================================================================

class BattleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_battles = bot.active_battles

# cogs/battle.py 의 BattleCog 클래스 내부

    async def _apply_damage(self, battle, attacker, target, base_damage):
        """단순화된 데미지 계산 헬퍼 함수"""
        multiplier = 1.0
        log_notes = []
        attacker_effects = attacker.get('effects', {})

        # 1. 특수 능력 버프 또는 크리티컬 확인
        if attacker.get('attack_buff_stacks', 0) > 0:
            multiplier = 1.5; attacker['attack_buff_stacks'] -= 1
            log_notes.append(f"✨ 강화된 공격(1.5배)!")
        
        # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
        elif attacker_effects.pop('guaranteed_crit', False): # Gut 스킬 효과
            multiplier = 2.0
            log_notes.append(f"💥 치명타 확정!")
        # ▲▲▲ 여기가 수정된 부분입니다 ▲▲▲

        elif random.random() < 0.10: # 기본 크리티컬 10%
            multiplier = 2.0
            log_notes.append(f"💥 치명타(2배)!")
        
        total_damage = round(base_damage * multiplier)

        # 상성 데미지 계산
        attribute_damage = 0
        advantages = {'Wit': 'Gut', 'Gut': 'Heart', 'Heart': 'Wit'}
        if attacker.get('attribute') and target.get('attribute'):
            # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
            attr_multiplier = attacker_effects.pop('attribute_multiplier', 1) # Wit 스킬 효과
            
            if advantages.get(attacker['attribute']) == target['attribute']:
                bonus = random.randint(0, attacker['level'] * 2) * attr_multiplier
                attribute_damage += bonus
                log_notes.append(f"👍 상성 우위 (+{bonus})")
            elif advantages.get(target['attribute']) == attacker['attribute']:
                penalty = random.randint(0, attacker['level'] * 2) * attr_multiplier
                attribute_damage -= penalty
                log_notes.append(f"👎 상성 열세 (-{penalty})")
        
        total_damage += attribute_damage
        # ▲▲▲ 여기가 수정된 부분입니다 ▲▲▲

        # 방어도 계산 및 소모
        defense = target.get('defense', 0)
        final_damage = max(0, total_damage - defense)
        defense_remaining = max(0, defense - total_damage)
        target['defense'] = defense_remaining
        
        # 최종 데미지 적용 및 로그 생성
        target['current_hp'] = max(0, target['current_hp'] - final_damage)
        log_message = f"💥 {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해!"
        if log_notes: log_message += " " + " ".join(log_notes)
        if defense > 0: log_message += f" (방어도 {defense} → {defense_remaining})"
        battle.add_log(log_message)
#============================================================================================================================

    @commands.command(name="대결")
    async def battle_request(self, ctx, opponent: discord.Member):
        if ctx.channel.id in self.active_battles: 
            return await ctx.send("이 채널에서는 이미 다른 활동이 진행중입니다.")
        if ctx.author == opponent: 
            return await ctx.send("자기 자신과는 대결할 수 없습니다.")
        
        all_data = load_data()
        p1_id, p2_id = str(ctx.author.id), str(opponent.id)
        if not all_data.get(p1_id, {}).get("registered", False) or not all_data.get(p2_id, {}).get("registered", False):
            return await ctx.send("두 플레이어 모두 `!등록`을 완료해야 합니다.")

        msg = await ctx.send(f"{opponent.mention}, {ctx.author.display_name}님의 대결 신청을 수락하시겠습니까? (30초 내 반응)")
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        def check(reaction, user):
            return user == opponent and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            if str(reaction.emoji) == "✅":
                await ctx.send("대결이 성사되었습니다! 전투를 시작합니다.")
                battle = Battle(ctx.channel, ctx.author, opponent, self.active_battles)
                self.active_battles[ctx.channel.id] = battle
                await battle.start_turn_timer()
                await battle.display_board()
            else:
                await ctx.send("대결이 거절되었습니다.")
        except asyncio.TimeoutError:
            await ctx.send("시간이 초과되어 대결이 취소되었습니다.")

    @commands.command(name="팀대결")
    async def team_battle_request(self, ctx, teammate: discord.Member, opponent1: discord.Member, opponent2: discord.Member):
        if ctx.channel.id in self.active_battles: 
            return await ctx.send("이 채널에서는 이미 전투가 진행중입니다.")
        
        players = {ctx.author, teammate, opponent1, opponent2}
        if len(players) < 4: 
            return await ctx.send("모든 플레이어는 서로 다른 유저여야 합니다.")
        
        all_data = load_data()
        for p in players:
            if not all_data.get(str(p.id), {}).get("registered", False): 
                return await ctx.send(f"{p.display_name}님은 아직 등록하지 않은 플레이어입니다.")

        msg = await ctx.send(f"**⚔️ 팀 대결 신청! ⚔️**\n\n**A팀**: {ctx.author.mention}, {teammate.mention}\n**B팀**: {opponent1.mention}, {opponent2.mention}\n\nB팀의 {opponent1.mention}, {opponent2.mention} 님! 대결을 수락하시면 30초 안에 ✅ 반응을 눌러주세요. (두 명 모두 수락해야 시작됩니다)")
        await msg.add_reaction("✅")
        
        accepted_opponents = set()
        def check(reaction, user): 
            return str(reaction.emoji) == '✅' and user.id in [opponent1.id, opponent2.id] and reaction.message.id == msg.id
        
        try:
            while len(accepted_opponents) < 2:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
                if user.id not in accepted_opponents:
                    accepted_opponents.add(user.id)
                    await ctx.send(f"✅ {user.display_name}님이 대결을 수락했습니다. (남은 인원: {2-len(accepted_opponents)}명)")
            
            await ctx.send("양 팀 모두 대결을 수락했습니다! 전투를 시작합니다.")
            team_a = [ctx.author, teammate]
            team_b = [opponent1, opponent2]
            battle = TeamBattle(ctx.channel, team_a, team_b, self.active_battles)
            self.active_battles[ctx.channel.id] = battle
            await battle.next_turn()
            
        except asyncio.TimeoutError: 
            return await ctx.send("시간이 초과되어 대결이 취소되었습니다.")
   
   
    async def get_current_player_and_battle(self, ctx):
        """PvP 전투 정보 및 현재 턴 플레이어를 확인하는 헬퍼 함수"""
        battle = self.active_battles.get(ctx.channel.id)
        if not battle: return None, None
        
        # Battle, TeamBattle 객체인지 확인 (향후 팀배틀 확장 대비)
        if not isinstance(battle, (Battle, TeamBattle)): return None, None

        current_player_id = battle.current_turn_player.id if isinstance(battle, Battle) else battle.current_turn_player_id
        
        if ctx.author.id != current_player_id: return None, None
        
        return battle, current_player_id
    



    @commands.command(name="이동")
    async def move(self, ctx, *directions):
        battle, _ = await self.get_current_player_and_battle(ctx)
        if not battle: return

        if battle.battle_type == "pve":
            return await ctx.send("사냥 중에는 이동할 수 없습니다.")

        p_stats = battle.players.get(ctx.author.id) if battle.battle_type == "pvp_team" else battle.get_player_stats(ctx.author)
        


        if battle.turn_actions_left <= 0:
            return await ctx.send("행동력이 없습니다.", delete_after=10)
        
        # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
        # 1. 플레이어의 효과(버프/디버프)를 확인합니다.
        effects = p_stats.get('effects', {})
        mobility_modifier = effects.get('mobility_modifier', 0)
        
        # 2. 기본 이동력에 효과를 더해 최종 이동력을 계산합니다.
        base_mobility = 2 if p_stats['class'] == '검사' else 1
        final_mobility = max(1, base_mobility + mobility_modifier) # 최소 이동력은 1
        # ▲▲▲ 여기가 수정된 부분입니다 ▲▲▲

        if not (1 <= len(directions) <= final_mobility):
            return await ctx.send(f"👉 현재 이동력은 **{final_mobility}**입니다. 1~{final_mobility}개의 방향을 입력해주세요.", delete_after=10)
        
        current_pos = p_stats['pos']; path = [current_pos]
        for direction in directions:
            next_pos = path[-1]
            # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
            lower_dir = direction.lower()
            if lower_dir == 'w': next_pos -= 5
            elif lower_dir == 's': next_pos += 5
            elif lower_dir == 'a': next_pos -= 1
            elif lower_dir == 'd': next_pos += 1
            else: # w, a, s, d가 아닌 다른 입력이 들어왔을 경우
                return await ctx.send(f"'{direction}'은(는) 잘못된 방향키입니다. `w, a, s, d`만 사용해주세요.", delete_after=10)
            if not (0 <= next_pos < 15) or (direction.lower() in 'ad' and path[-1] // 5 != next_pos // 5): return await ctx.send("❌ 맵 밖으로 이동할 수 없습니다.", delete_after=10)
            path.append(next_pos)
        final_pos = path[-1]
        occupied_positions = []
        if battle.battle_type == "pvp_1v1": occupied_positions.append(battle.get_opponent_stats(ctx.author)['pos'])
        else: occupied_positions = [p['pos'] for p_id, p in battle.players.items() if p_id != ctx.author.id]
        if final_pos in occupied_positions: return await ctx.send("❌ 다른 플레이어가 있는 칸으로 이동할 수 없습니다.", delete_after=10)
        battle.grid[current_pos] = "□"; battle.grid[final_pos] = p_stats['emoji']; p_stats['pos'] = final_pos
        battle.add_log(f"🚶 {p_stats['name']}이(가) 이동했습니다."); await battle.handle_action_cost(1)


#============================================================================================================================




    @commands.command(name="공격")
    async def attack(self, ctx, target_user: discord.Member = None):
        battle = self.active_battles.get(ctx.channel.id)
        if not battle or not isinstance(battle, Battle): return
        if ctx.author.id != battle.current_turn_player.id: return
        if battle.turn_actions_left <= 0: return await ctx.send("행동력이 없습니다.")

        attacker = battle.get_player_stats(ctx.author)
        target = battle.get_opponent_stats(ctx.author)
        
        distance = battle.get_distance(attacker['pos'], target['pos'])
        can_attack, attack_type = False, ""
        if attacker['class'] == '마법사' and 2 <= distance <= 3: can_attack, attack_type = True, "원거리"
        elif attacker['class'] == '마검사' and (distance == 1 or 2 <= distance <= 3): attack_type = "근거리" if distance == 1 else "원거리"; can_attack = True
        elif attacker['class'] == '검사' and distance == 1: can_attack, attack_type = True, "근거리"
        
        if not can_attack: return await ctx.send("❌ 공격 사거리가 아닙니다.")
        
        base_damage = attacker['physical'] + random.randint(0, attacker['mental']) if attack_type == "근거리" else attacker['mental'] + random.randint(0, attacker['physical'])
        await self._apply_damage(battle, attacker, target, base_damage)
        
        if target['current_hp'] <= 0:
            await battle.end_battle(ctx.author, f"{target['name']}이(가) 공격을 받고 쓰러졌습니다!")
            if ctx.channel.id in self.active_battles: del self.active_battles[ctx.channel.id]
        else: await battle.handle_action_cost(1)


#============================================================================================================================


    @commands.command(name="특수")
    async def special_ability(self, ctx):
        battle, _ = await self.get_current_player_and_battle(ctx)
        if not battle: return

        # PvE에서는 비활성화
        if battle.battle_type == "pve":
            return await ctx.send("사냥 중에는 이 명령어를 사용할 수 없습니다.")

        # PvP 공통 조건 확인
        if battle.turn_actions_left <= 0: 
            return await ctx.send("행동력이 없습니다.", delete_after=10)
        
        p_stats = battle.players.get(ctx.author.id) if battle.battle_type == "pvp_team" else battle.get_player_stats(ctx.author)
        
        if p_stats.get('special_cooldown', 0) > 0: 
            return await ctx.send(f"스킬/특수 능력의 쿨타임이 {p_stats['special_cooldown']}턴 남았습니다.", delete_after=10)

        # 기본 직업별 특수 능력
        player_class = p_stats['class']
        
        if player_class == '마법사':
            occupied_positions = []
            if battle.battle_type == "pvp_1v1":
                occupied_positions.append(battle.get_opponent_stats(ctx.author)['pos'])
            else: # pvp_team
                occupied_positions = [p['pos'] for p_id, p in battle.players.items() if p_id != ctx.author.id]
            
            empty_cells = [str(i + 1) for i in range(15) if i not in occupied_positions]
            if not empty_cells: return await ctx.send("이동할 수 있는 빈 칸이 없습니다.")
            
            await ctx.send(f"**텔레포트**: 이동할 위치의 번호를 입력해주세요.\n> 가능한 위치: `{'`, `'.join(empty_cells)}`")
            def check(m): return m.author == ctx.author and m.channel == ctx.channel and m.content in empty_cells
            try:
                msg = await self.bot.wait_for('message', check=check, timeout=15.0)
                target_pos = int(msg.content) - 1
                battle.grid[p_stats['pos']] = "□"; p_stats['pos'] = target_pos; battle.grid[target_pos] = p_stats['emoji']
                battle.add_log(f"✨ {p_stats['name']}이(가) {target_pos + 1}번 위치로 텔레포트했습니다!")
            except asyncio.TimeoutError: 
                return await ctx.send("시간이 초과되어 취소되었습니다.")

        elif player_class == '마검사':
            p_stats['attack_buff_stacks'] = 1
            battle.add_log(f"✨ {p_stats['name']}이 검에 마력을 주입합니다! 다음 공격이 강화됩니다.")

        elif player_class == '검사':
            p_stats['current_hp'] = max(1, p_stats['current_hp'] - p_stats['level'])
            p_stats['attack_buff_stacks'] = 2
            battle.add_log(f"🩸 {p_stats['name']}이(가) 체력을 소모하여 다음 2회 공격을 강화합니다!")

        # 공통 후속 처리
        p_stats['special_cooldown'] = 2 
        await battle.handle_action_cost(1)




#============================================================================================================================

# cogs/battle.py 의 BattleCog 클래스 내부

    @commands.command(name="스킬")
    async def use_skill(self, ctx, target_user: discord.Member = None):
        battle, _ = await self.get_current_player_and_battle(ctx)
        if not battle: return

        if battle.turn_actions_left <= 0: return await ctx.send("행동력이 없습니다.", delete_after=10)
        
        attacker = battle.players.get(ctx.author.id) if battle.battle_type == "pvp_team" else battle.get_player_stats(ctx.author)
        
        player_attribute = attacker.get("attribute")
        if not player_attribute: return await ctx.send("속성을 부여받은 후에 스킬을 사용할 수 있습니다. (`!속성부여`)")

        if attacker.get('special_cooldown', 0) > 0: return await ctx.send(f"스킬/특수 능력의 쿨타임이 {attacker['special_cooldown']}턴 남았습니다.", delete_after=10)

        targets_to_affect = []
        if battle.battle_type == "pvp_team":
            team_ids = battle.team_a_ids if attacker['id'] in battle.team_a_ids else battle.team_b_ids
            targets_to_affect = [battle.players[pid] for pid in team_ids]
        else: # pvp_1v1
            targets_to_affect.append(attacker)

        # 2. 속성에 따라 결정된 대상들에게 효과를 적용합니다.
        if player_attribute == "Gut":
            battle.add_log(f"✊ {attacker['name']}이(가) Gut 속성의 스킬을 사용합니다!")
            for p_stat in targets_to_affect:
                p_stat.setdefault('effects', {})['guaranteed_crit'] = True
            battle.add_log("모든 아군의 다음 공격이 치명타로 적용됩니다!")

        elif player_attribute == "Wit":
            battle.add_log(f"🧐 {attacker['name']}이(가) Wit 속성의 스킬을 사용합니다!")
            for p_stat in targets_to_affect:
                p_stat.setdefault('effects', {})['attribute_multiplier'] = 3
            battle.add_log("모든 아군의 다음 공격 상성 효과가 3배로 증폭됩니다!")

        elif player_attribute == "Heart":
            battle.add_log(f"💚 {attacker['name']}이(가) Heart 속성의 스킬을 사용합니다!")
            healed_players = []
            for p_stat in targets_to_affect:
                heal_amount = round(p_stat['max_hp'] * 0.3)
                p_stat['current_hp'] = min(p_stat['max_hp'], p_stat['current_hp'] + heal_amount)
                healed_players.append(f"{p_stat['name']}(+{heal_amount})")
            battle.add_log(f"아군 전체의 체력이 회복되었습니다. ({', '.join(healed_players)})")

        # --- PvP 스킬 사용 후 공통 처리 ---
        attacker['special_cooldown'] = 2
        await battle.handle_action_cost(1)

        # 이 스킬들은 직접적인 데미지를 주지 않으므로, 전투 종료 확인 로직이 필요 없습니다.

#============================================================================================================================



    @commands.command(name="기권")
    async def forfeit(self, ctx):
        battle = self.active_battles.get(ctx.channel.id)
        if not battle: return

        # battle_type 꼬리표로 분기
        if battle.battle_type == "pve":
            await ctx.send("사냥 중에는 기권이 아닌 `!도망`을 사용해주십시오.")
        
        elif battle.battle_type == "pvp_1v1":
            if ctx.author.id in [battle.p1_user.id, battle.p2_user.id]:
                winner_user = battle.p2_user if ctx.author.id == battle.p1_user.id else battle.p1_user
                await battle.end_battle(winner_user, f"{ctx.author.display_name}님이 기권했습니다.")
                if ctx.channel.id in self.active_battles: del self.active_battles[ctx.channel.id]
            else:
                await ctx.send("당신은 이 전투의 참여자가 아닙니다.")

        elif battle.battle_type == "pvp_team":
            winner_team_name, winner_ids, reason = None, None, None
            if ctx.author.id in battle.team_a_ids:
                winner_team_name, winner_ids, reason = "B팀", battle.team_b_ids, f"A팀의 {ctx.author.display_name}님이 기권했습니다."
            elif ctx.author.id in battle.team_b_ids:
                winner_team_name, winner_ids, reason = "A팀", battle.team_a_ids, f"B팀의 {ctx.author.display_name}님이 기권했습니다."
            else:
                return await ctx.send("당신은 이 전투의 참여자가 아닙니다.")

            await battle.end_battle(winner_team_name, winner_ids, reason)
            if ctx.channel.id in self.active_battles: del self.active_battles[ctx.channel.id]




async def setup(bot):
    await bot.add_cog(BattleCog(bot))
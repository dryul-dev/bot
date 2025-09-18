
import discord
from discord.ext import commands
import json
import os
import random
import asyncio
from cogs.monster import PveBattle # monsterCog의 PveBattle 클래스를 사용하기 위해 import

DATA_FILE = "player_data.json"

def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

# ▼▼▼ 여기에 아래 두 클래스를 붙여넣으세요 ▼▼▼

# --- 1:1 전투 관리 클래스 ---
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
        player_id = str(user.id); base_stats = all_data[player_id]
        level = 1 + ((base_stats['mental'] + base_stats['physical']) // 5)
        max_hp = max(1, level * 10 + base_stats['physical'])
        if base_stats.get("rest_buff_active", False):
            hp_buff = level * 5; max_hp += hp_buff
            self.add_log(f"🌙 {base_stats['name']}이(가) 휴식 효과로 최대 체력이 {hp_buff} 증가합니다!")
            all_data[player_id]["rest_buff_active"] = False; save_data(all_data)

        
        return {"id": user.id, 
                "name": base_stats['name'], 
                "emoji": base_stats['emoji'], 
                "class": base_stats['class'], 
                "attribute": base_stats.get("attribute"), 
                "advanced_class": base_stats.get("advanced_class"), 
                "defense": 0, "effects": {}, 
                "color": int(base_stats['color'][1:], 16), 
                "mental": base_stats['mental'], 
                "physical": base_stats['physical'], 
                "level": level, 
                "max_hp": max_hp, 
                "current_hp": max_hp, 
                "pos": -1, 
                "special_cooldown": 0, 
                "double_damage_buff": 0,
                }

    def get_player_stats(self, user):
        return self.p1_stats if user.id == self.p1_user.id else self.p2_stats

    def get_opponent_stats(self, user):
        return self.p2_stats if user.id == self.p1_user.id else self.p1_stats

    def add_log(self, message):
        self.battle_log.append(message)
        if len(self.battle_log) > 5:
            self.battle_log.pop(0)

    async def display_board(self, extra_message=""):
        turn_player_stats = self.get_player_stats(self.current_turn_player)
        embed = discord.Embed(title="⚔️ 1:1 대결 진행중 ⚔️", description=f"**현재 턴: {turn_player_stats['name']}**", color=turn_player_stats['color'])
        grid_str = "".join([f" `{cell}` " + ("\n" if (i + 1) % 5 == 0 else "") for i, cell in enumerate(self.grid)])
        embed.add_field(name="[ 전투 맵 ]", value=grid_str, inline=False)
        for p_stats in [self.p1_stats, self.p2_stats]:
            adv_class = p_stats.get('advanced_class') or p_stats['class']
            embed.add_field(name=f"{p_stats['emoji']} {p_stats['name']} ({adv_class})", value=f"**HP: {p_stats['current_hp']} / {p_stats['max_hp']}**", inline=True)
        embed.add_field(name="남은 행동", value=f"{self.turn_actions_left}회", inline=False)
        embed.add_field(name="📜 전투 로그", value="\n".join(self.battle_log), inline=False)
        if extra_message: embed.set_footer(text=extra_message)
        await self.channel.send(embed=embed)

    async def handle_action_cost(self, cost=1):
        self.turn_actions_left -= cost
        if self.turn_actions_left <= 0:
            await self.display_board("행동력을 모두 소모하여 턴을 종료합니다."); await asyncio.sleep(2); await self.next_turn()
        else: await self.display_board()

# cogs/battle.py 의 Battle 클래스 내부

    async def next_turn(self):
        # ▼▼▼ 지속 효과 처리를 위해 추가된 부분 ▼▼▼
        # 다음 턴이 될 플레이어 객체를 미리 찾음
        next_player_user = self.p2_user if self.current_turn_player.id == self.p1_user.id else self.p1_user
        next_p_stats = self.get_player_stats(next_player_user)
        effects = next_p_stats.get('effects', {})

        # 지속 회복 효과가 있는지 확인하고 적용
        if 'heal_over_time' in effects:
            hot_data = effects['heal_over_time']
            heal_amount = hot_data['amount']
            next_p_stats['current_hp'] = min(next_p_stats['max_hp'], next_p_stats['current_hp'] + heal_amount)
            self.add_log(f"💚 지속 회복 효과로 {next_p_stats['name']}의 체력이 {heal_amount} 회복되었습니다.")
            hot_data['duration'] -= 1
            if hot_data['duration'] <= 0:
                del effects['heal_over_time']
        # ▲▲▲ 여기까지 추가된 부분 ▲▲▲

        # 기존 턴 넘기는 로직
        p_stats = self.get_player_stats(self.current_turn_player)
        if p_stats.get('special_cooldown', 0) > 0: p_stats['special_cooldown'] -= 1
        
        self.current_turn_player = next_player_user
        self.turn_actions_left = 2
        
        # 행동 횟수 증감 효과 적용
        if 'action_point_modifier' in effects:
            self.turn_actions_left += effects['action_point_modifier']
            self.add_log(f"⏱️ 효과로 인해 {next_p_stats['name']}의 행동 횟수가 조정됩니다!")
        next_p_stats['effects'] = {} # 1회성 효과는 여기서 초기화

        self.add_log(f"▶️ {next_p_stats['name']}의 턴입니다.")
        await self.start_turn_timer()
        await self.display_board()


    async def start_turn_timer(self):
        if self.turn_timer: self.turn_timer.cancel()
        self.turn_timer = asyncio.create_task(self.timeout_task())


    async def timeout_task(self):
        try:
            await asyncio.sleep(300) # 5분
            
            # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
            # 현재 턴 플레이어(패배자)로부터 상대방(승리자)의 '객체'를 찾습니다.
            loser_user = self.current_turn_player
            winner_user = self.p2_user if loser_user.id == self.p1_user.id else self.p1_user
            
            await self.end_battle(winner_user, f"시간 초과로 {loser_user.display_name}님이 패배했습니다.")
            # ▲▲▲ 여기가 수정된 부분입니다 ▲▲▲
            
            # 전투가 종료되었으므로 active_battles에서 직접 제거
            if self.channel.id in self.active_battles: 
                del self.active_battles[self.channel.id]
        except asyncio.CancelledError: 
            pass

    async def end_battle(self, winner_user, reason):
        if self.turn_timer: self.turn_timer.cancel()
        winner_stats = self.get_player_stats(winner_user)
        all_data = load_data(); winner_id = str(winner_user.id)
        if winner_id in all_data:
            all_data[winner_id]['school_points'] = all_data[winner_id].get('school_points', 0) + 10; save_data(all_data)
        embed = discord.Embed(title="🎉 전투 종료! 🎉", description=f"**승자: {winner_stats['name']}**\n> {reason}\n\n**획득: 10 스쿨 포인트**", color=winner_stats['color'])
        await self.channel.send(embed=embed)
        
    def get_coords(self, pos): return pos // 5, pos % 5
    def get_distance(self, pos1, pos2): r1, c1 = self.get_coords(pos1); r2, c2 = self.get_coords(pos2); return max(abs(r1 - r2), abs(c1 - c2))

# --- 팀 전투 관리 클래스 ---
class TeamBattle(Battle):
    def __init__(self, channel, team_a_users, team_b_users, active_battles_ref):
        self.channel = channel; self.active_battles = active_battles_ref; self.players = {}; self.battle_log = ["팀 전투가 시작되었습니다!"]; self.battle_type = "pvp_team"
        self.team_a_ids = [p.id for p in team_a_users]; self.team_b_ids = [p.id for p in team_b_users]
        all_data = load_data()
        for player_user in team_a_users + team_b_users: self.players[player_user.id] = self._setup_player_stats(all_data, player_user)
        self.players[team_a_users[0].id]['pos'] = 0; self.players[team_a_users[1].id]['pos'] = 10
        self.players[team_b_users[0].id]['pos'] = 4; self.players[team_b_users[1].id]['pos'] = 14
        self.grid = ["□"] * 15
        for p_id, p_stats in self.players.items(): self.grid[p_stats['pos']] = p_stats['emoji']
        if random.random() < 0.5: self.turn_order = [team_a_users[0].id, team_b_users[0].id, team_a_users[1].id, team_b_users[1].id]; self.add_log("▶️ A팀이 선공입니다!")
        else: self.turn_order = [team_b_users[0].id, team_a_users[0].id, team_b_users[1].id, team_a_users[1].id]; self.add_log("▶️ B팀이 선공입니다!")
        self.turn_index = -1; self.current_turn_player_id = None; self.turn_actions_left = 2; self.turn_timer = None
    
# cogs/battle.py 의 TeamBattle 클래스 내부

    async def next_turn(self):
        # ▼▼▼ 지속 효과 처리를 위해 추가된 부분 ▼▼▼
        # 다음 턴 인덱스를 미리 계산하여 다음 플레이어 ID를 찾음
        next_turn_index = (self.turn_index + 1) % 4
        next_player_id = self.turn_order[next_turn_index]
        next_p_stats = self.players[next_player_id]
        effects = next_p_stats.get('effects', {})
        
        # 지속 회복 효과가 있는지 확인하고 적용
        if 'heal_over_time' in effects:
            hot_data = effects['heal_over_time']
            heal_amount = hot_data['amount']
            next_p_stats['current_hp'] = min(next_p_stats['max_hp'], next_p_stats['current_hp'] + heal_amount)
            self.add_log(f"💚 지속 회복 효과로 {next_p_stats['name']}의 체력이 {heal_amount} 회복되었습니다.")
            hot_data['duration'] -= 1
            if hot_data['duration'] <= 0:
                del effects['heal_over_time']
        # ▲▲▲ 여기까지 추가된 부분 ▲▲▲

        # 기존 턴 넘기는 로직
        self.turn_index = next_turn_index
        
        if self.players[next_player_id]['current_hp'] <= 0:
            self.add_log(f"↪️ {self.players[next_player_id]['name']}님은 리타이어하여 턴을 건너뜁니다.")
            await self.display_board(); await asyncio.sleep(1.5); await self.next_turn(); return

        self.current_turn_player_id = next_player_id
        self.turn_actions_left = 2
        
        # 행동 횟수 증감 효과 적용
        if 'action_point_modifier' in effects:
            self.turn_actions_left += effects['action_point_modifier']
            self.add_log(f"⏱️ 효과로 인해 {next_p_stats['name']}의 행동 횟수가 조정됩니다!")
        next_p_stats['effects'] = {} # 1회성 효과는 여기서 초기화
        
        if next_p_stats.get('special_cooldown', 0) > 0: next_p_stats['special_cooldown'] -= 1
        
        self.add_log(f"▶️ {next_p_stats['name']}의 턴입니다.")
        await self.start_turn_timer()
        await self.display_board()


    async def timeout_task(self):
        """5분이 지나면 타임아웃으로 패배 처리하는 함수"""
        try:
            await asyncio.sleep(300) # 5분
            
            # 현재 턴 플레이어(패배자)의 팀을 찾습니다.
            loser_player_id = self.current_turn_player_id
            if loser_player_id in self.team_a_ids:
                winner_team_name, winner_ids = "B팀", self.team_b_ids
            else:
                winner_team_name, winner_ids = "A팀", self.team_a_ids
            
            loser_name = self.players[loser_player_id]['name']
            await self.end_battle(winner_team_name, winner_ids, f"시간 초과로 {loser_name}님의 턴이 종료되어 상대팀이 승리했습니다.")

            # 전투가 종료되었으므로 active_battles에서 직접 제거
            if self.channel.id in self.active_battles: 
                del self.active_battles[self.channel.id]

        except asyncio.CancelledError:
            pass # 타이머가 정상적으로 취소된 경우
            await self.display_board()

    async def display_board(self, extra_message=""):
        turn_player_stats = self.players[self.current_turn_player_id]
        embed = discord.Embed(title="⚔️ 팀 대결 진행중 ⚔️", description=f"**현재 턴: {turn_player_stats['name']}**", color=turn_player_stats['color'])
        grid_str = "".join([f" `{cell}` " + ("\n" if (i + 1) % 5 == 0 else "") for i, cell in enumerate(self.grid)])
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
        all_data = load_data(); point_log = []
        for winner_id in winner_ids:
            winner_id_str = str(winner_id)
            if winner_id_str in all_data:
                all_data[winner_id_str]['school_points'] = all_data[winner_id_str].get('school_points', 0) + 15
                winner_name = self.players[winner_id]['name']; point_log.append(f"{winner_name}: +15P")
        save_data(all_data)
        winner_representative_stats = self.players[winner_ids[0]]
        embed = discord.Embed(title=f"🎉 {winner_team_name} 승리! 🎉", description=f"> {reason}\n\n**획득: 15 스쿨 포인트**\n" + "\n".join(point_log), color=winner_representative_stats['color'])
        await self.channel.send(embed=embed)

# ▲▲▲ 여기까지 붙여넣으세요 ▲▲▲

# --- BattleCog 클래스 ---
class BattleCog(commands.Cog):
    # ...
    def __init__(self, bot):
        self.bot = bot
        self.active_battles = bot.active_battles

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
        
        # 헬퍼 함수
# cogs/battle.py 의 BattleCog 클래스 내부

    async def get_current_player_and_battle(self, ctx):
        """모든 전투 명령어에서 공통으로 사용할 플레이어 및 전투 정보 확인 함수"""
        battle = self.active_battles.get(ctx.channel.id)
        if not battle: return None, None
        
        current_player_id = None
        if hasattr(battle, 'battle_type'):
            if battle.battle_type == "pve":
                if battle.current_turn != "player": return None, None
                current_player_id = battle.player_stats['id']
            elif battle.battle_type in ["pvp_1v1", "pvp_team"]:
                current_player_id = battle.current_turn_player.id if battle.battle_type == "pvp_1v1" else battle.current_turn_player_id
        
        if not current_player_id or ctx.author.id != current_player_id: return None, None
        return battle, current_player_id

    # 행동 명령어들
    @commands.command(name="이동")
    async def move(self, ctx, *directions):
        battle, _ = await self.get_current_player_and_battle(ctx)
        if not battle: return

        if battle.battle_type == "pve":
            return await ctx.send("사냥 중에는 이동할 수 없습니다.")

        if battle.turn_actions_left <= 0:
            return await ctx.send("행동력이 없습니다.", delete_after=10)

        p_stats = battle.players.get(ctx.author.id) if battle.battle_type == "pvp_team" else battle.get_player_stats(ctx.author)
        
        effects = p_stats.get('effects', {}); mobility_modifier = effects.get('mobility_modifier', 0)
        base_mobility = 2 if p_stats['class'] == '검사' else 1
        final_mobility = max(1, base_mobility + mobility_modifier)

        if not (1 <= len(directions) <= final_mobility):
            return await ctx.send(f"👉 현재 이동력은 **{final_mobility}**입니다. 1~{final_mobility}개의 방향을 입력해주세요.", delete_after=10)
        
        current_pos = p_stats['pos']; path = [current_pos]
        for direction in directions:
            next_pos = path[-1]
            if direction.lower() == 'w': next_pos -= 5
            elif direction.lower() == 's': next_pos += 5
            elif direction.lower() == 'a': next_pos -= 1
            elif direction.lower() == 'd': next_pos += 1
            if not (0 <= next_pos < 15) or (direction.lower() in 'ad' and path[-1] // 5 != next_pos // 5):
                return await ctx.send("❌ 맵 밖으로 이동할 수 없습니다.", delete_after=10)
            path.append(next_pos)
        
        final_pos = path[-1]
        
        occupied_positions = []
        if battle.battle_type == "pvp_1v1":
            occupied_positions.append(battle.get_opponent_stats(ctx.author)['pos'])
        else: # pvp_team
            occupied_positions = [p['pos'] for p_id, p in battle.players.items() if p_id != ctx.author.id]
        if final_pos in occupied_positions:
            return await ctx.send("❌ 다른 플레이어가 있는 칸으로 이동할 수 없습니다.", delete_after=10)
        
        battle.grid[current_pos] = "□"; battle.grid[final_pos] = p_stats['emoji']; p_stats['pos'] = final_pos
        battle.add_log(f"🚶 {p_stats['name']}이(가) 이동했습니다.")
        await battle.handle_action_cost(1)

    @commands.command(name="공격")
    async def attack(self, ctx, target_user: discord.Member = None):
        battle, current_player_id = await self.get_current_player_and_battle(ctx)
        if not battle: return

        attacker, target = None, None
        
        # --- 1. 공격자 및 타겟 정보 설정 ---
        if battle.battle_type == "pve":
            attacker = battle.player_stats
            target = battle.monster_stats
        elif battle.battle_type == "pvp_1v1":
            opponent_user = battle.p2_user if ctx.author.id == battle.p1_user.id else battle.p1_user
            target_user = target_user or opponent_user
            attacker = battle.get_player_stats(ctx.author)
            target = battle.get_player_stats(target_user)
        elif battle.battle_type == "pvp_team":
            if not target_user: return await ctx.send("팀 대결에서는 공격 대상을 `@멘션`으로 지정해주세요.")
            if target_user.id not in battle.players: return await ctx.send("유효하지 않은 대상입니다.", delete_after=10)
            is_opponent = (ctx.author.id in battle.team_a_ids and target_user.id in battle.team_b_ids) or \
                          (ctx.author.id in battle.team_b_ids and target_user.id in battle.team_a_ids)
            if not is_opponent: return await ctx.send("❌ 같은 팀원은 공격할 수 없습니다.", delete_after=10)
            attacker = battle.players[ctx.author.id]
            target = battle.players[target_user.id]

        if not attacker or not target: return

        # --- 2. 공격 가능 여부 확인 ---
        can_attack, attack_type = False, ""
        if battle.battle_type == "pve":
            can_attack = True
            attack_type = "근거리" if attacker['class'] == '검사' else ("근거리" if attacker.get('physical', 0) >= attacker.get('mental', 0) else "원거리")
# cogs/battle.py 의 attack 함수 내부

        else: # PvP
            distance = battle.get_distance(attacker['pos'], target['pos'])
            if attacker['class'] == '마법사' and 2 <= distance <= 3: # ◀◀ 이 부분을 수정
                can_attack, attack_type = True, "원거리"
            elif attacker['class'] == '마검사':
                if distance == 1: can_attack, attack_type = True, "근거리"
                elif 2 <= distance <= 3: can_attack, attack_type = True, "원거리"
            elif attacker['class'] == '검사' and distance == 1: 
                can_attack, attack_type = True, "근거리"
        
        if not can_attack: return await ctx.send("❌ 공격 사거리가 아닙니다.", delete_after=10)
        
        # --- 3. 데미지 계산 ---
        base_damage = attacker['physical'] + random.randint(0, attacker['mental']) if attack_type == "근거리" else attacker['mental'] + random.randint(0, attacker['physical'])
        multiplier, attribute_damage = 1.0, 0
        
        attacker_effects = attacker.get('effects', {})
        if 'next_attack_multiplier' in attacker_effects:
            multiplier = attacker_effects.pop('next_attack_multiplier', 1.0); battle.add_log(f"✨ 영창 효과! 데미지가 {multiplier}배 증폭!")

        elif attacker.get('double_damage_buff', 0) > 0:
            multiplier = 2.0; attacker['double_damage_buff'] -= 1
            battle.add_log(f"✨ 강화된 공격! 데미지가 2배로 적용됩니다! (남은 횟수: {attacker['double_damage_buff']}회)")
        elif random.random() < 0.10: 
            multiplier = 2.0; battle.add_log(f"💥 치명타 발생!")
        else:
            if attacker['class'] == '마법사': multiplier = 1.2
            elif attacker['class'] == '검사': multiplier = 1.2
            
        advantages = {'Wit': 'Gut', 'Gut': 'Heart', 'Heart': 'Wit'}
        if attacker.get('attribute') and target.get('attribute'):
            if advantages.get(attacker['attribute']) == target['attribute']:
                bonus = random.randint(0, attacker['level']); attribute_damage += bonus; battle.add_log(f"👍 상성 우위! +{bonus} 데미지!")
            elif advantages.get(target['attribute']) == attacker['attribute']:
                penalty = random.randint(0, attacker['level']); attribute_damage -= penalty; battle.add_log(f"👎 상성 열세... -{penalty} 데미지")
        
        final_damage = max(1, round(base_damage * multiplier) + attribute_damage - target.get('defense', 0))

        target['current_hp'] = max(0, target['current_hp'] - final_damage)
        battle.add_log(f"💥 {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해를 입혔습니다!")

        if target['current_hp'] <= 0:
            if battle.battle_type == "pve":
                await battle.end_battle(win=True)
            elif battle.battle_type == "pvp_1v1":
                await battle.end_battle(ctx.author, f"{target['name']}이(가) 공격을 받고 쓰러졌습니다!")
                if ctx.channel.id in self.active_battles: del self.active_battles[ctx.channel.id]
            elif battle.battle_type == "pvp_team":
                if await battle.check_game_over(): 
                    if ctx.channel.id in self.active_battles: del self.active_battles[ctx.channel.id]
        else:
            if battle.battle_type == "pve":
                await battle.monster_turn()
            else: # PvP
                await battle.handle_action_cost(1)



        
    @commands.command(name="특수")
    async def special_ability(self, ctx):
        # 1. 헬퍼 함수로 턴 확인을 한번에 끝냅니다.
        battle, current_player_id = await self.get_current_player_and_battle(ctx)
        if not battle: return

        # 2. PvE 상황에서는 사용 불가 처리
        if battle.battle_type == "pve":
            return await ctx.send("사냥 중에는 기본 특수 능력을 사용할 수 없습니다. (`!스킬`을 사용해주세요)")

        # 3. PvP 행동력 및 쿨다운 확인
        if battle.turn_actions_left <= 0:
            return await ctx.send("행동력이 없습니다.", delete_after=10)
        
        # 4. 플레이어 정보 가져오기 (Battle, TeamBattle 모두 처리)
        p_stats = battle.players.get(current_player_id) if battle.battle_type == "pvp_team" else battle.get_player_stats(ctx.author)
            
        if p_stats.get('special_cooldown', 0) > 0:
            return await ctx.send(f"쿨타임이 {p_stats['special_cooldown']}턴 남았습니다.", delete_after=10)


        # 4. 직업별 특수 능력 시전
        player_class = p_stats['class']
        
        if player_class == '마법사':
            empty_cells = [str(i+1) for i, cell in enumerate(battle.grid) if cell == "□"]
            await ctx.send(f"**텔레포트**: 이동할 위치의 번호를 입력해주세요. (1~15)\n> 가능한 위치: `{'`, `'.join(empty_cells)}`")
            def check(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit() and 1 <= int(m.content) <= 15
            try:
                msg = await self.bot.wait_for('message', check=check, timeout=30.0)
                target_pos = int(msg.content) - 1
                
                occupied_positions = []
                if isinstance(battle, Battle):
                    occupied_positions.append(battle.get_opponent_stats(ctx.author)['pos'])
                else: # TeamBattle
                    occupied_positions = [p['pos'] for p_id, p in battle.players.items() if p_id != ctx.author.id]

                if battle.grid[target_pos] != "□" or target_pos in occupied_positions:
                    return await ctx.send("해당 위치는 비어있지 않습니다. 다시 시도해주세요.")
                
                battle.grid[p_stats['pos']] = "□"
                p_stats['pos'] = target_pos
                battle.grid[target_pos] = p_stats['emoji']
                battle.add_log(f"✨ {p_stats['name']}이(가) {target_pos+1}번 위치로 텔레포트했습니다!")
            except asyncio.TimeoutError: 
                return await ctx.send("시간이 초과되어 취소되었습니다.")

        elif player_class == '마검사':
            # 'double_damage_buff' 횟수를 1로 설정합니다.
            p_stats['double_damage_buff'] = p_stats.get('double_damage_buff', 0) + 1
            battle.add_log(f"✨ {p_stats['name']}이(가) 검에 마력을 주입합니다! 다음 공격이 강화됩니다!")

        elif player_class == '검사':
            self_damage = p_stats['level']
            p_stats['current_hp'] = max(1, p_stats['current_hp'] - self_damage)
            p_stats['double_damage_buff'] = 2
            battle.add_log(f"🩸 {p_stats['name']}이(가) 자신의 체력을 소모하여 다음 2회 공격을 강화합니다!")

        # 5. 쿨다운 및 행동력 소모
        p_stats['special_cooldown'] = 2 
        await battle.handle_action_cost(1)

    @commands.command(name="스킬")
    async def use_skill(self, ctx, skill_number: int, target_user: discord.Member = None):
        battle, current_player_id = await self.get_current_player_and_battle(ctx)
        if not battle: return

        attacker = None
        if battle.battle_type == "pve":
            attacker = battle.player_stats
        elif battle.battle_type in ["pvp_1v1", "pvp_team"]:
            if battle.turn_actions_left <= 0: return await ctx.send("행동력이 없습니다.", delete_after=10)
            attacker = battle.players.get(current_player_id) if battle.battle_type == "pvp_team" else battle.get_player_stats(ctx.author)

        if not attacker: return
        if not attacker.get("advanced_class"): return await ctx.send("스킬은 상위 직업으로 전직한 플레이어만 사용할 수 있습니다.")
        if attacker.get('special_cooldown', 0) > 0: return await ctx.send(f"스킬/특수 능력의 쿨타임이 {attacker['special_cooldown']}턴 남았습니다.", delete_after=10)

        # --- PvE 로직 ---
        if battle.battle_type == "pve":
            if skill_number != 1: return await ctx.send("사냥 중에는 1번 스킬만 사용할 수 있습니다.")
            advanced_class = attacker['advanced_class']
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

    # --- PvP 로직 ---
        elif battle.battle_type in ["pvp_1v1", "pvp_team"]:
            if not target_user: return await ctx.send("PvP에서는 스킬 대상을 `@멘션`으로 지정해야 합니다.")
            
            target = None
            if battle.battle_type == "pvp_team":
                if target_user.id in battle.players: target = battle.players[target_user.id]
            else: # pvp_1v1
                if target_user.id in [battle.p1_user.id, battle.p2_user.id]: target = battle.get_player_stats(target_user)
            
            if not target: return await ctx.send("유효하지 않은 대상입니다.", delete_after=10)
            
            advanced_class = attacker['advanced_class']
            # --- PvP 전용 스킬 로직 ---
            if advanced_class == "캐스터":
                distance = battle.get_distance(attacker['pos'], target['pos'])
                if not (2 <= distance <= 3): return await ctx.send("❌ 원거리 공격 사거리가 아닙니다.", delete_after=10)

                if skill_number == 1:
                    base_damage = attacker['mental'] + random.randint(0, attacker['physical']); multiplier = 2.0 if random.random() < 0.5 else 1.5
                    if multiplier == 2.0: battle.add_log(f"💥 캐스터의 주문이 치명타로 적중!")
                    final_damage = max(1, round(base_damage * multiplier) - target.get('defense', 0)); target['current_hp'] = max(0, target['current_hp'] - final_damage)
                    battle.add_log(f"☄️ {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해!")
                elif skill_number == 2: target.setdefault('effects', {})['mobility_modifier'] = -1; battle.add_log(f"🌀 {attacker['name']}이(가) {target['name']}의 다음 턴 이동력을 1 감소!")
                elif skill_number == 3: # 다음 턴 첫 공격 3배 (10% 확률)
                    if random.random() < 0.10:
                        attacker.setdefault('effects', {})['next_attack_multiplier'] = 3.0
                        battle.add_log(f"✨ {attacker['name']} 주문 영창 성공! 다음 공격 3배!")
                    else: battle.add_log(f"💨 {attacker['name']}의 주문 영창이 실패했다...")
                else: return await ctx.send("잘못된 스킬 번호입니다.")
            
            elif advanced_class == "힐러":
                if skill_number == 1: heal_amount = round(target['max_hp'] * 0.4); target['current_hp'] = min(target['max_hp'], target['current_hp'] + heal_amount); battle.add_log(f"💖 {attacker['name']}이(가) {target['name']}의 체력을 {heal_amount}만큼 회복!")
                elif skill_number == 2: target.setdefault('effects', {})['mobility_modifier'] = 1; battle.add_log(f"🍃 {attacker['name']}이(가) {target['name']}의 다음 턴 이동력을 1 증가!")
                else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)


            elif advanced_class == "파이오니어":
                if skill_number == 1: # 체력 소모 후 80% 크리티컬 원거리 공격
                    if not (2 <= battle.get_distance(attacker['pos'], target['pos']) <= 3): return await ctx.send("❌ 원거리 공격 사거리가 아닙니다.")
                    self_damage = attacker['level']; attacker['current_hp'] = max(1, attacker['current_hp'] - self_damage); battle.add_log(f"🩸 {attacker['name']}이(가) 체력을 {self_damage} 소모!")
                    base_damage = attacker['mental'] + random.randint(0, attacker['physical'])
                    multiplier = 2.0 if random.random() < 0.8 else 1.5
                    if multiplier == 2.0: battle.add_log(f"🔥 파이오니어의 마력 폭발!")
                    final_damage = max(1, round(base_damage * multiplier) - target.get('defense', 0)); target['current_hp'] = max(0, target['current_hp'] - final_damage)
                    battle.add_log(f"☄️ {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해!")
                
                elif skill_number == 2: # 광역 공격
                    if battle.battle_type != "pvp_team": return await ctx.send("이 스킬은 팀 대결에서만 사용할 수 있습니다.")
                    base_damage = attacker['mental'] + random.randint(0, attacker['physical'])
                    final_damage = max(1, round(base_damage * 1.5) - target.get('defense', 0)) # 광역기는 1.5배 고정
                    
                    enemy_team_ids = battle.team_b_ids if current_player_id in battle.team_a_ids else battle.team_a_ids
                    for enemy_id in enemy_team_ids:
                        battle.players[enemy_id]['current_hp'] = max(0, battle.players[enemy_id]['current_hp'] - final_damage)
                    battle.add_log(f"☄️ {attacker['name']}이(가) 적군 전체에게 **{final_damage}**의 광역 피해!")
                    
                    if random.random() < 0.10:
                        teammate_ids = [pid for pid in (battle.team_a_ids if current_player_id in battle.team_a_ids else battle.team_b_ids) if pid != current_player_id]
                        if teammate_ids:
                            hit_teammate_id = random.choice(teammate_ids)
                            battle.players[hit_teammate_id]['current_hp'] = max(0, battle.players[hit_teammate_id]['current_hp'] - final_damage)
                            battle.add_log(f"마력에 휩쓸린 팀원 **{battle.players[hit_teammate_id]['name']}**이(가) 피해!")

                elif skill_number == 3: # 1.5배 근거리 공격
                    if battle.get_distance(attacker['pos'], target['pos']) != 1: return await ctx.send("❌ 근거리 공격 사거리가 아닙니다.")
                    base_damage = attacker['physical'] + random.randint(0, attacker['mental'])
                    final_damage = max(1, round(base_damage * 1.5) - target.get('defense', 0))
                    target['current_hp'] = max(0, target['current_hp'] - final_damage)
                    battle.add_log(f"🔪 {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해!")
                else: return await ctx.send("잘못된 스킬 번호입니다.")






            
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


            elif advanced_class == "그랜터":
                if skill_number == 1: # 다음 공격 1.5배 부여
                    target.setdefault('effects', {})['next_attack_multiplier'] = 1.5
                    battle.add_log(f"✨ {attacker['name']}이(가) {target['name']}에게 힘을 부여! 다음 공격 1.5배 강화!")
                elif skill_number == 2: # 2턴간 체력 회복
                    target.setdefault('effects', {})['heal_over_time'] = {'amount': round(target['max_hp'] / 5), 'duration': 2}
                    battle.add_log(f"💚 {attacker['name']}이(가) {target['name']}에게 지속 회복 효과를 부여!")
                else: return await ctx.send("잘못된 스킬 번호입니다.")







            
            elif advanced_class == "워리어":
                if skill_number == 1: # 레벨만큼 체력 감소 후, 크리티컬 80% 근거리 공격
                    if battle.get_distance(attacker['pos'], target['pos']) != 1: return await ctx.send("❌ 근거리 공격 사거리가 아닙니다.")
                    
                    self_damage = attacker['level']
                    attacker['current_hp'] = max(1, attacker['current_hp'] - self_damage)
                    battle.add_log(f"🩸 {attacker['name']}이(가) 체력을 {self_damage} 소모합니다!")

                    base_damage = attacker['physical'] + random.randint(0, attacker['mental'])
                    multiplier = 2.0 if random.random() < 0.8 else 1.2 # 크리티컬 80%
                    if multiplier == 2.0: battle.add_log(f"‼️ 워리어의 강타!")
                    
                    final_damage = max(1, round(base_damage * multiplier) - target.get('defense', 0))
                    target['current_hp'] = max(0, target['current_hp'] - final_damage)
                    battle.add_log(f"⚔️ {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해!")

                elif skill_number == 2: # 대상 행동 횟수 감소
                    target.setdefault('effects', {})['action_point_modifier'] = -1
                    battle.add_log(f"⛓️ {attacker['name']}이(가) {target['name']}의 다음 턴 행동 횟수를 1회 감소!")
                else: return await ctx.send("잘못된 스킬 번호입니다.")

            elif advanced_class == "디펜더":
                if skill_number == 1: defense_gain = attacker['level'] * 4; target['defense'] += defense_gain; battle.add_log(f"🛡️ {attacker['name']}이(가) {target['name']}에게 방어도 **{defense_gain}** 부여!")
                elif skill_number == 2: target.setdefault('effects', {})['action_point_modifier'] = 1; battle.add_log(f"🏃 {attacker['name']}이(가) {target['name']}의 다음 턴 행동 횟수를 1회 증가!")
                else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)



            elif advanced_class == "커맨더":
                if skill_number == 1: # 공격 멀티플라이어 1.5의 근거리 공격
                    if battle.get_distance(attacker['pos'], target['pos']) != 1: return await ctx.send("❌ 근거리 공격 사거리가 아닙니다.")
                    base_damage = attacker['physical'] + random.randint(0, attacker['mental'])
                    final_damage = max(1, round(base_damage * 1.5) - target.get('defense', 0))
                    target['current_hp'] = max(0, target['current_hp'] - final_damage)
                    battle.add_log(f"📜 {attacker['name']}의 전술 공격! {target['name']}에게 **{final_damage}**의 피해!")
                
                elif skill_number == 2: # 팀원 이동
                    if battle.battle_type != "pvp_team":
                        return await ctx.send("이 스킬은 팀 대결에서만 사용할 수 있습니다.")

                    # 타겟이 같은 팀원인지 확인
                    attacker_team_ids = battle.team_a_ids if attacker['id'] in battle.team_a_ids else battle.team_b_ids
                    if target['id'] not in attacker_team_ids:
                        return await ctx.send("자신의 팀원에게만 사용할 수 있습니다.")
                    if target['id'] == attacker['id']:
                        return await ctx.send("자기 자신은 이동시킬 수 없습니다.")

                    # 이동 가능한 빈 칸 목록 생성
                    occupied_positions = [p['pos'] for p in battle.players.values()]
                    empty_cells_indices = [i for i in range(15) if i not in occupied_positions]
                    empty_cells_numbers = [str(i + 1) for i in empty_cells_indices]

                    if not empty_cells_numbers:
                        return await ctx.send("이동할 수 있는 빈 칸이 없습니다.")

                    # 사용자에게 위치 입력받기
                    await ctx.send(f"**전술적 재배치**: **{target['name']}**님을 이동시킬 위치의 번호를 입력해주세요.\n> 가능한 위치: `{'`, `'.join(empty_cells_numbers)}`")
                    def check(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit() and m.content in empty_cells_numbers
                    try:
                        msg = await self.bot.wait_for('message', check=check, timeout=30.0)
                        target_pos = int(msg.content) - 1
                        
                        # 이동 실행
                        battle.grid[target['pos']] = "□"
                        target['pos'] = target_pos
                        battle.grid[target_pos] = target['emoji']
                        battle.add_log(f"🧭 {attacker['name']}이(가) {target['name']}을(를) {target_pos + 1}번 위치로 재배치했습니다!")

                    except asyncio.TimeoutError:
                        return await ctx.send("시간이 초과되어 취소되었습니다.")

                elif skill_number == 3: # 팀원 2배 버프 (10% 확률)
                    if random.random() < 0.10:
                        targets_to_buff = []
                        if battle.battle_type == "pvp_team":
                            targets_to_buff = [battle.players[pid] for pid in (battle.team_a_ids if current_player_id in battle.team_a_ids else battle.team_b_ids)]
                        else: # 1v1
                            targets_to_buff.append(attacker)
                        
                        for p_stat in targets_to_buff:
                            p_stat.setdefault('effects', {})['next_attack_multiplier'] = 2.0
                        battle.add_log(f"😠 {attacker['name']}의 사기 주입! {target['name']}의 다음 공격이 2배 강화됩니다!")
                    else: battle.add_log(f"💨 {attacker['name']}의 의지가 닿지 않았다...")
                else: return await ctx.send("잘못된 스킬 번호입니다.")

            # --- PvP 스킬 사용 후 공통 처리 ---
        attacker['special_cooldown'] = 2
        await battle.handle_action_cost(1)
        
        if battle.battle_type == "pvp_team":
            if await battle.check_game_over(): del self.active_battles[ctx.channel.id]
        elif target['current_hp'] <= 0:
            await battle.end_battle(ctx.author, f"{target['name']}이(가) 스킬에 맞아 쓰러졌습니다!")
            del self.active_battles[ctx.channel.id]
        return

# cogs/battle.py 의 BattleCog 클래스 내부

    @commands.command(name="기권")
    async def forfeit(self, ctx):
        battle = self.active_battles.get(ctx.channel.id)
        if not battle: return

        # battle_type 꼬리표로 분기
        if battle.battle_type == "pve":
            if ctx.author.id == battle.player_user.id:
                await battle.end_battle(win=False, reason=f"{ctx.author.display_name}님이 사냥을 포기했습니다.")
            else:
                await ctx.send("당신은 현재 사냥 중이 아닙니다.")
        
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



    @commands.command(name="전직변경")
    @commands.is_owner()
    async def change_advanced_class(self, ctx, target_name: str, *, new_class_name: str):
        """[관리자용] 등록된 이름으로 유저의 상위 클래스를 강제로 변경하고, 기본 직업도 함께 변경합니다."""
        
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

        # 2. 변경할 상위 클래스가 존재하는지, 그리고 그에 맞는 기본 직업과 속성은 무엇인지 찾기
        new_base_class, new_attribute = None, None
        for base_class, options in self.ADVANCED_CLASSES.items():
            for attr, adv_class in options.items():
                if adv_class == new_class_name:
                    new_base_class = base_class
                    new_attribute = attr
                    break
            if new_base_class:
                break
        
        if not new_base_class:
            return await ctx.send(f"'{new_class_name}'(이)라는 상위 클래스는 존재하지 않습니다.")

        # 3. 데이터 업데이트
        old_base_class = target_data.get("class", "없음")
        old_adv_class = target_data.get("advanced_class", "없음")
        
        all_data[target_id]["class"] = new_base_class
        all_data[target_id]["advanced_class"] = new_class_name
        all_data[target_id]["attribute"] = new_attribute
        save_data(all_data)

        # 4. 결과 알림
        embed = discord.Embed(
            title="✨ 전직 관리 완료 (전체 변경)",
            description=f"**{target_name}**님의 직업을 성공적으로 변경했습니다.",
            color=discord.Color.purple()
        )
        embed.add_field(name="대상", value=target_name, inline=True)
        embed.add_field(name="기본 직업 변경", value=f"`{old_base_class}` → `{new_base_class}`", inline=False)
        embed.add_field(name="상위 클래스 변경", value=f"`{old_adv_class}` → `{new_class_name}` ({new_attribute} 속성)", inline=False)
        await ctx.send(embed=embed)



    @change_advanced_class.error
    async def change_ac_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("이 명령어는 봇 소유자만 사용할 수 있습니다.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("사용법: `!전직변경 [이름] [상위클래스이름]`\n> 예시: `!전직변경 홍길동 캐스터`")
        # ▼▼▼ 여기가 추가된 부분입니다 ▼▼▼
        else:
            # 터미널(screen)에만 자세한 오류 내용을 출력합니다. (디버깅용)
            print(f"!전직변경 명령어에서 예상치 못한 오류 발생: {error}")
            # 디스코드 채널에는 간단한 안내 메시지만 보냅니다.
            await ctx.send("알 수 없는 오류가 발생하여 명령을 처리할 수 없습니다. 봇 소유자에게 문의해주세요.")
        # ▲▲▲ 여기가 추가된 부분입니다 ▲▲▲
async def setup(bot):
    await bot.add_cog(BattleCog(bot))



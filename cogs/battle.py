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
        max_hp = max(1, level * 10 + base_stats['physical'] * 2)
        if base_stats.get("rest_buff_active", False):
            hp_buff = level * 5; max_hp += hp_buff
            self.add_log(f"🌙 {base_stats['name']}이(가) 휴식 효과로 최대 체력이 {hp_buff} 증가합니다!")
            all_data[player_id]["rest_buff_active"] = False; save_data(all_data)
        
        equipped_gear = base_stats.get("equipped_gear", [])
        gear_damage_bonus = 0
        # PvP에서는 장비 효과가 적용되지 않으므로 이 부분은 비워둡니다.

        return {"id": user.id, "name": base_stats['name'], "emoji": base_stats['emoji'], "class": base_stats['class'], "attribute": base_stats.get("attribute"), "advanced_class": base_stats.get("advanced_class"), "defense": 0, "effects": {}, "color": int(base_stats['color'][1:], 16), "mental": base_stats['mental'], "physical": base_stats['physical'], "level": level, "max_hp": max_hp, "current_hp": max_hp, "pos": -1, "special_cooldown": 0, "attack_buff_stacks": 0}

    def get_player_stats(self, user): return self.p1_stats if user.id == self.p1_user.id else self.p2_stats
    def get_opponent_stats(self, user): return self.p2_stats if user.id == self.p1_user.id else self.p1_stats
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

    async def next_turn(self):
        # 다음 턴 플레이어의 지속 효과 먼저 처리
        next_player_user = self.p2_user if self.current_turn_player.id == self.p1_user.id else self.p1_user
        next_p_stats = self.get_player_stats(next_player_user); effects = next_p_stats.get('effects', {})
        if 'heal_over_time' in effects:
            hot_data = effects['heal_over_time']; heal_amount = hot_data['amount']
            next_p_stats['current_hp'] = min(next_p_stats['max_hp'], next_p_stats['current_hp'] + heal_amount)
            self.add_log(f"💚 지속 회복 효과로 {next_p_stats['name']}의 체력이 {heal_amount} 회복되었습니다.")
            hot_data['duration'] -= 1
            if hot_data['duration'] <= 0: del effects['heal_over_time']
        
        # 현재 턴 플레이어의 쿨다운 처리
        p_stats = self.get_player_stats(self.current_turn_player)
        if p_stats.get('special_cooldown', 0) > 0: p_stats['special_cooldown'] -= 1
        
        # 턴 전환
        self.current_turn_player = next_player_user
        self.turn_actions_left = 2
        
        # 행동 횟수 증감 효과 적용
        if 'action_point_modifier' in effects:
            self.turn_actions_left += effects['action_point_modifier']
            self.add_log(f"⏱️ 효과로 인해 {next_p_stats['name']}의 행동 횟수가 조정됩니다!")

        # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
        # 지속되어야 하는 효과 목록
        persistent_effects = ['heal_over_time', 'next_attack_multiplier']
        # 지속 효과를 제외한 1회성 효과만 제거
        next_p_stats['effects'] = {k: v for k, v in effects.items() if k in persistent_effects}
        # ▲▲▲ 여기가 수정된 부분입니다 ▲▲▲

        self.add_log(f"▶️ {next_p_stats['name']}의 턴입니다.")
        await self.start_turn_timer()
        await self.display_board()

    async def start_turn_timer(self):
        if self.turn_timer: self.turn_timer.cancel()
        self.turn_timer = asyncio.create_task(self.timeout_task())
    async def timeout_task(self):
        try:
            await asyncio.sleep(300)
            loser_user = self.current_turn_player
            winner_user = self.p2_user if loser_user.id == self.p1_user.id else self.p1_user
            await self.end_battle(winner_user, f"시간 초과로 {loser_user.display_name}님이 패배했습니다.")
            if self.channel.id in self.active_battles: del self.active_battles[self.channel.id]
        except asyncio.CancelledError: pass

    async def end_battle(self, winner_user, reason):
        if self.turn_timer: self.turn_timer.cancel()
        winner_stats = self.get_player_stats(winner_user)
        all_data = load_data(); winner_id = str(winner_user.id)
        if winner_id in all_data:
            all_data[winner_id]['school_points'] = all_data[winner_id].get('school_points', 0) + 10; save_data(all_data)
        embed = discord.Embed(title="🎉 전투 종료! 🎉", description=f"**승자: {winner_stats['name']}**\n> {reason}\n\n**획득: 10 스쿨 포인트**", color=winner_stats['color'])
        await self.channel.send(embed=embed)
        
    def get_coords(self, pos): return pos // 5, pos % 5
    def get_distance(self, pos1, pos2): r1, c1 = self.get_coords(pos1); r2, c2 = self.get_coords(pos2); return abs(r1 - r2) + abs(c1 - c2)

# cogs/battle.py 파일 내부

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
    
    async def next_turn(self):
        # 다음 턴 인덱스 계산
        next_turn_index = (self.turn_index + 1) % 4
        next_player_id = self.turn_order[next_turn_index]
        next_p_stats = self.players[next_player_id]
        effects = next_p_stats.get('effects', {})
        
        # 다음 턴 플레이어의 지속 효과 먼저 처리
        if 'heal_over_time' in effects:
            hot_data = effects['heal_over_time']
            heal_amount = hot_data['amount']
            next_p_stats['current_hp'] = min(next_p_stats['max_hp'], next_p_stats['current_hp'] + heal_amount)
            self.add_log(f"💚 지속 회복 효과로 {next_p_stats['name']}의 체력이 {heal_amount} 회복되었습니다.")
            hot_data['duration'] -= 1
            if hot_data['duration'] <= 0:
                del effects['heal_over_time']

        # 턴 전환
        self.turn_index = next_turn_index
        
        # 리타이어한 플레이어 턴 건너뛰기
        if next_p_stats['current_hp'] <= 0:
            self.add_log(f"↪️ {next_p_stats['name']}님은 리타이어하여 턴을 건너뜁니다.")
            await self.display_board()
            await asyncio.sleep(1.5)
            await self.next_turn()
            return

        self.current_turn_player_id = next_player_id
        self.turn_actions_left = 2
        
        if 'action_point_modifier' in effects:
            self.turn_actions_left += effects['action_point_modifier']
            self.add_log(f"⏱️ 효과로 인해 {next_p_stats['name']}의 행동 횟수가 조정됩니다!")
        
        # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
        persistent_effects = ['heal_over_time', 'next_attack_multiplier']
        next_p_stats['effects'] = {k: v for k, v in effects.items() if k in persistent_effects}
        # ▲▲▲ 여기가 수정된 부분입니다 ▲▲▲
        
        if next_p_stats.get('special_cooldown', 0) > 0: next_p_stats['special_cooldown'] -= 1
        
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
                winner_name = self.players[winner_id]['name']; point_log.append(f"{winner_name}: +15P")
        save_data(all_data)
        winner_representative_stats = self.players[winner_ids[0]]
        embed = discord.Embed(title=f"🎉 {winner_team_name} 승리! 🎉", description=f"> {reason}\n\n**획득: 15 스쿨 포인트**\n" + "\n".join(point_log), color=winner_representative_stats['color'])
        await self.channel.send(embed=embed)

#============================================================================================================================

class BattleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_battles = bot.active_battles


    async def get_current_player_and_battle(self, ctx):
        """[최종 수정본] 모든 전투 명령어에서 공통으로 사용할 플레이어 및 전투 정보 확인 함수"""
        battle = self.active_battles.get(ctx.channel.id)
        if not battle: return None, None
        
        current_player_id = None
        # battle_type 꼬리표로 현재 전투 종류를 명확하게 확인
        if hasattr(battle, 'battle_type'):
            if battle.battle_type == "pve":
                if battle.current_turn != "player": return None, None
                current_player_id = battle.player_stats['id']
            elif battle.battle_type in ["pvp_1v1", "pvp_team"]:
                current_player_id = battle.current_turn_player.id if battle.battle_type == "pvp_1v1" else battle.current_turn_player_id
        
        # 명령어 사용자와 현재 턴 플레이어가 일치하는지 최종 확인
        if not current_player_id or ctx.author.id != current_player_id: return None, None
        
        return battle, current_player_id



    async def _apply_damage(self, battle, attacker, target, base_damage, base_multiplier=1.0, crit_chance=0.1):
        """[최종 수정본] PvP 데미지 계산 및 적용을 전담하는 함수"""
        
        final_multiplier = base_multiplier
        log_notes = []
        attacker_effects = attacker.get('effects', {})

        # --- 1. 멀티플라이어 우선순위 적용 ---
        if 'next_attack_multiplier' in attacker_effects:
            final_multiplier = attacker_effects.pop('next_attack_multiplier', 1.0)
            log_notes.append(f"✨ 부여 효과({final_multiplier}배)!")
        elif attacker.get('attack_buff_stacks', 0) > 0:
            final_multiplier = 1.5; attacker['attack_buff_stacks'] -= 1
            log_notes.append(f"✨ 강화된 공격(1.5배)!")
        elif random.random() < crit_chance:
            final_multiplier = 2.0
            log_notes.append(f"💥 치명타(2배)!")
        elif base_multiplier == 1.0:
            if attacker['class'] == '마법사': final_multiplier = 1.2
            elif attacker['class'] == '검사': final_multiplier = 1.2
        
        # --- 2. 상성 계산 ---
        attribute_damage = 0
        advantages = {'Wit': 'Gut', 'Gut': 'Heart', 'Heart': 'Wit'}
        if attacker.get('attribute') and target.get('attribute'):
            if advantages.get(attacker['attribute']) == target['attribute']:
                bonus = random.randint(0, attacker['level'] * 2); attribute_damage += bonus
                log_notes.append(f"👍 상성 우위(+{bonus})")
            elif advantages.get(target['attribute']) == attacker['attribute']:
                penalty = random.randint(0, attacker['level'] * 2); attribute_damage -= penalty
                log_notes.append(f"👎 상성 열세({penalty})")

        # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
        # --- 3. 방어 계산 및 소모 ---
        total_damage = round(base_damage * final_multiplier) + attribute_damage
        defense = target.get('defense', 0)
        
        final_damage = max(0, total_damage - defense)
        defense_remaining = max(0, defense - total_damage)
        target['defense'] = defense_remaining # 소모된 방어도를 반영
        
        # --- 4. 최종 데미지 적용 및 로그 생성 ---
        target['current_hp'] = max(0, target['current_hp'] - final_damage)

        log_message = f"💥 {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해!"
        if log_notes: log_message += " " + " ".join(log_notes)
        if defense > 0:
            log_message += f" (방어도 {defense} → {defense_remaining})"
        
        battle.add_log(log_message)
        # ▲▲▲ 여기가 수정된 부분입니다 ▲▲▲


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
# cogs/battle.py 의 BattleCog 클래스 내부

    async def get_current_player_and_battle(self, ctx):
        """[최종 수정본] 모든 전투 명령어에서 공통으로 사용할 플레이어 및 전투 정보 확인 함수"""
        battle = self.active_battles.get(ctx.channel.id)
        if not battle: return None, None
        
        current_player_id = None
        # battle_type 꼬리표로 현재 전투 종류를 명확하게 확인
        if hasattr(battle, 'battle_type'):
            if battle.battle_type == "pve":
                if battle.current_turn != "player": return None, None
                current_player_id = battle.player_stats['id']
            elif battle.battle_type in ["pvp_1v1", "pvp_team"]:
                current_player_id = battle.current_turn_player.id if battle.battle_type == "pvp_1v1" else battle.current_turn_player_id
        
        # 명령어 사용자와 현재 턴 플레이어가 일치하는지 최종 확인
        if not current_player_id or ctx.author.id != current_player_id: return None, None
        
        return battle, current_player_id

# cogs/battle.py 의 BattleCog 클래스 내부

    

    @commands.command(name="이동")
    async def move(self, ctx, *directions):
        battle, _ = await self.get_current_player_and_battle(ctx)
        if not battle: return
        if battle.battle_type == "pve": return await ctx.send("사냥 중에는 이동할 수 없습니다.")
        if battle.turn_actions_left <= 0: return await ctx.send("행동력이 없습니다.", delete_after=10)
        p_stats = battle.players.get(ctx.author.id) if battle.battle_type == "pvp_team" else battle.get_player_stats(ctx.author)
        effects = p_stats.get('effects', {}); mobility_modifier = effects.get('mobility_modifier', 0)
        base_mobility = 2 if p_stats['class'] == '검사' else 1; final_mobility = max(1, base_mobility + mobility_modifier)
        if not (1 <= len(directions) <= final_mobility): return await ctx.send(f"👉 현재 이동력은 **{final_mobility}**입니다. 1~{final_mobility}개의 방향을 입력해주세요.", delete_after=10)
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
        battle, _ = await self.get_current_player_and_battle(ctx)
        if not battle: return

        # --- PvE 로직 ---
        if battle.battle_type == "pve":
            attacker = battle.player_stats
            target = battle.monster_stats
            attack_type = "근거리" if attacker['class'] == '검사' else ("근거리" if attacker.get('physical', 0) >= attacker.get('mental', 0) else "원거리")
            
            base_damage = attacker['physical'] + random.randint(0, attacker['mental']) if attack_type == "근거리" else attacker['mental'] + random.randint(0, attacker['physical'])
            final_damage = max(1, round(base_damage) + attacker.get('gear_damage_bonus', 0) - target.get('defense', 0))
            
            target['current_hp'] = max(0, target['current_hp'] - final_damage)
            log_message = f"💥 {attacker['name']}이(가) {target['name']}에게 **{final_damage}**의 피해를 입혔습니다!"
            battle.add_log(log_message)
            await ctx.send(log_message); await asyncio.sleep(1.5)

            # PvE 전용 후속 처리
            if target['current_hp'] <= 0:
                await battle.end_battle(win=True)
            else:
                await battle.monster_turn()
            return # PvE 로직은 여기서 완전히 종료

        # --- PvP 로직 (헬퍼 함수 사용) ---
        elif battle.battle_type in ["pvp_1v1", "pvp_team"]:
            # 1. 공격자, 타겟, 사거리 등 기본 정보 설정
            attacker, target = None, None
            if battle.battle_type == "pvp_1v1":
                opponent_user = battle.p2_user if ctx.author.id == battle.p1_user.id else battle.p1_user
                target_user = target_user or opponent_user
                attacker = battle.get_player_stats(ctx.author)
                target = battle.get_player_stats(target_user)
            else: # pvp_team
                if not target_user: return await ctx.send("팀 대결에서는 공격 대상을 `@멘션`으로 지정해주세요.")
                if target_user.id not in battle.players: return await ctx.send("유효하지 않은 대상입니다.")
                is_opponent = (ctx.author.id in battle.team_a_ids and target_user.id in battle.team_b_ids) or \
                              (ctx.author.id in battle.team_b_ids and target_user.id in battle.team_a_ids)
                if not is_opponent: return await ctx.send("❌ 같은 팀원은 공격할 수 없습니다.")
                attacker = battle.players[ctx.author.id]
                target = battle.players[target_user.id]
            
            if not attacker or not target: return

            distance = battle.get_distance(attacker['pos'], target['pos'])
            can_attack, attack_type = False, ""
            if attacker['class'] == '마법사' and 2 <= distance <= 3: can_attack, attack_type = True, "원거리"
            elif attacker['class'] == '마검사' and (distance == 1 or 2 <= distance <= 3):
                attack_type = "근거리" if distance == 1 else "원거리"; can_attack = True
            elif attacker['class'] == '검사' and distance == 1: can_attack, attack_type = True, "근거리"
            
            if not can_attack: return await ctx.send("❌ 공격 사거리가 아닙니다.", delete_after=10)

            # 2. 기본 데미지만 계산
            base_damage = attacker['physical'] + random.randint(0, attacker['mental']) if attack_type == "근거리" else attacker['mental'] + random.randint(0, attacker['physical'])
            
            # 3. 헬퍼 함수를 호출하여 모든 복잡한 계산 및 데미지 적용 실행
            await self._apply_damage(battle, attacker, target, base_damage)

            # 4. PvP 후속 처리
            if target['current_hp'] <= 0:
                battle.add_log(f"☠️ {target['name']}이(가) 쓰러졌습니다!")
                if battle.battle_type == "pvp_team":
                    if await battle.check_game_over(): del self.active_battles[ctx.channel.id]
                    else: await battle.display_board()
                else: # pvp_1v1
                    await battle.end_battle(ctx.author, f"{target['name']}이(가) 공격을 받고 쓰러졌습니다!")
                    del self.active_battles[ctx.channel.id]
            else:
                await battle.handle_action_cost(1)


#============================================================================================================================



    @commands.command(name="특수")
    async def special_ability(self, ctx):
        battle, _ = await self.get_current_player_and_battle(ctx)
        if not battle: return
        if battle.battle_type == "pve": return await ctx.send("사냥 중에는 특수 능력을 사용할 수 없습니다.")
        if battle.turn_actions_left <= 0: return await ctx.send("행동력이 없습니다.", delete_after=10)
        p_stats = battle.players.get(ctx.author.id) if battle.battle_type == "pvp_team" else battle.get_player_stats(ctx.author)
        if p_stats.get('special_cooldown', 0) > 0: return await ctx.send(f"쿨타임이 {p_stats['special_cooldown']}턴 남았습니다.")
        
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
            p_stats['attack_buff_stacks'] = p_stats.get('attack_buff_stacks', 0) + 1
            battle.add_log(f"✨ {p_stats['name']}이 검에 마력을 주입합니다! 다음 공격이 강화됩니다.")


        elif player_class == '검사':
            p_stats['current_hp'] = max(1, p_stats['current_hp'] - p_stats['level'])
            p_stats['attack_buff_stacks'] = 2
            battle.add_log(f"🩸 {p_stats['name']}이(가) 체력을 소모하여 다음 2회 공격을 강화합니다!")
        
        p_stats['special_cooldown'] = 2 
        await battle.handle_action_cost(1)


#============================================================================================================================



    @commands.command(name="스킬")
    async def use_skill(self, ctx, skill_number: int, target_user: discord.Member = None):
        battle, current_player_id = await self.get_current_player_and_battle(ctx)
        if not battle: return

        # --- PvE에서는 스킬 사용 불가 처리 ---
        if battle.battle_type == "pve":
            return await ctx.send("사냥 중에는 스킬을 사용할 수 없습니다.")

        # --- 이하 PvP 전용 로직 ---
        if battle.turn_actions_left <= 0: 
            return await ctx.send("행동력이 없습니다.", delete_after=10)
        
        attacker = battle.players.get(current_player_id) if battle.battle_type == "pvp_team" else battle.get_player_stats(ctx.author)
        
        if not attacker.get("advanced_class"): 
            return await ctx.send("스킬은 상위 직업으로 전직한 플레이어만 사용할 수 있습니다.")
        if attacker.get('special_cooldown', 0) > 0: 
            return await ctx.send(f"스킬/특수 능력의 쿨타임이 {attacker['special_cooldown']}턴 남았습니다.", delete_after=10)

        if not target_user: 
            return await ctx.send("PvP에서는 스킬 대상을 `@멘션`으로 지정해야 합니다.")
        
        target = None
        if battle.battle_type == "pvp_team":
            if target_user.id in battle.players: 
                target = battle.players[target_user.id]
        else: # pvp_1v1
            if target_user.id in [battle.p1_user.id, battle.p2_user.id]: 
                target = battle.get_player_stats(target_user)
        
        if not target: 
            return await ctx.send("유효하지 않은 대상입니다.", delete_after=10)
        
        advanced_class = attacker['advanced_class']
        if advanced_class == "워리어":
            if skill_number == 1: # 데미지를 주는 스킬
                if battle.get_distance(attacker['pos'], target['pos']) != 1: return await ctx.send("❌ 근거리 공격 사거리가 아닙니다.")
                
                self_damage = attacker['level']
                attacker['current_hp'] = max(1, attacker['current_hp'] - self_damage)
                battle.add_log(f"🩸 {attacker['name']}이(가) 체력을 {self_damage} 소모합니다!")

                base_damage = attacker['physical'] + random.randint(0, attacker['mental']) 

                await self._apply_damage(battle, attacker, target, base_damage, crit_chance=0.8)
            elif skill_number == 2: # 대상 행동 횟수 감소
                target.setdefault('effects', {})['action_point_modifier'] = -1
                battle.add_log(f"⛓️ {attacker['name']}이(가) {target['name']}의 다음 턴 행동 횟수를 1회 감소!")
            else: return await ctx.send("잘못된 스킬 번호입니다.")



        elif advanced_class == "디펜더":
            if skill_number == 1: defense_gain = attacker['level'] * 5; target['defense'] += defense_gain; battle.add_log(f"🛡️ {attacker['name']}이(가) {target['name']}에게 방어도 **{defense_gain}** 부여!")
            elif skill_number == 2: target.setdefault('effects', {})['action_point_modifier'] = 1; battle.add_log(f"🏃 {attacker['name']}이(가) {target['name']}의 다음 턴 행동 횟수를 1회 증가!")
            else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)

        elif advanced_class == "커맨더":
            if skill_number == 1: # 공격 멀티플라이어 1.5의 근거리 공격
                if battle.get_distance(attacker['pos'], target['pos']) != 1: return await ctx.send("❌ 근거리 공격 사거리가 아닙니다.")

                # 1. 기본 데미지만 계산
                base_damage = attacker['physical'] + random.randint(0, attacker['mental'])

                # 2. 1.5의 배율을 헬퍼 함수에 전달하여 모든 계산을 맡김
                await self._apply_damage(battle, attacker, target, base_damage, base_multiplier=1.5)
                        
            elif skill_number == 2: # 자신 또는 팀원 이동
                # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
                # 1. 1:1 대결 또는 팀 대결인지 확인
                if battle.battle_type not in ["pvp_1v1", "pvp_team"]:
                    return await ctx.send("이 스킬은 PvP 대결에서만 사용할 수 있습니다.")

                # 2. 타겟 유효성 검사
                if battle.battle_type != "pvp_team": 
                    return await ctx.send("이 스킬은 팀 대결에서만 사용할 수 있습니다.")
                    
                else: # pvp_team
                    attacker_team_ids = battle.team_a_ids if attacker['id'] in battle.team_a_ids else battle.team_b_ids
                    if target['id'] not in attacker_team_ids:
                        return await ctx.send("팀원에게만 사용할 수 있습니다.")
                # ▲▲▲ 여기가 수정된 부분입니다 ▲▲▲

                # 3. 이하 이동 로직은 기존과 동일
                occupied_positions = [p['pos'] for p_id, p in battle.players.items() if p_id != target['id']] if battle.battle_type == "pvp_team" else [battle.get_opponent_stats(ctx.author)['pos']]
                empty_cells = [str(i + 1) for i in range(15) if i not in occupied_positions]
                if not empty_cells: return await ctx.send("이동할 수 있는 빈 칸이 없습니다.")
                
                await ctx.send(f"**전술적 재배치**: **{target['name']}**님을 이동시킬 위치의 번호를 입력해주세요.\n> 가능한 위치: `{'`, `'.join(empty_cells)}`")
                def check(m):
                        print("\n--- [DEBUG] check 함수 실행 ---")
                        
                        cond1 = m.author == ctx.author
                        print(f"1. 작성자 일치 여부 ({m.author.name} == {ctx.author.name}): {cond1}")
                        
                        cond2 = m.channel == ctx.channel
                        print(f"2. 채널 일치 여부 (#{m.channel.name} == #{ctx.channel.name}): {cond2}")
                        
                        # empty_cell_numbers 변수 이름을 다시 한번 확인해주세요.
                        # 이전 답변에서는 empty_cell_numbers 로 통일했습니다.
                        cond3 = m.content in empty_cells 
                        print(f"3. 입력 내용('{m.content}')이 목록에 포함되는지 여부: {cond3}")
                        print(f"   (비교 대상 목록: {empty_cells})")
                        
                        result = cond1 and cond2 and cond3
                        print(f"--> 최종 결과: {result}")
                        return result
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
            else: return await ctx.send("잘못된 스킬 번호입니다.")


        elif advanced_class == "캐스터":
            if skill_number == 1: # 크리티컬 50% 원거리 공격
                distance = battle.get_distance(attacker['pos'], target['pos'])
                if not (2 <= distance <= 3): return await ctx.send("❌ 원거리 공격 사거리가 아닙니다.")
                
                base_damage = attacker['mental'] + random.randint(0, attacker['physical'])
                attacker.setdefault('effects', {})['skill_crit_chance'] = 0.5
        
                    
                    # 2. 헬퍼 함수를 호출합니다.
                await self._apply_damage(battle, attacker, target, base_damage)

            elif skill_number == 2: target.setdefault('effects', {})['mobility_modifier'] = -1; battle.add_log(f"🌀 {attacker['name']}이(가) {target['name']}의 다음 턴 이동력을 1 감소!")
            else: return await ctx.send("잘못된 스킬 번호입니다.")

        elif advanced_class == "힐러":
            if skill_number == 1: heal_amount = round(target['max_hp'] * 0.4); target['current_hp'] = min(target['max_hp'], target['current_hp'] + heal_amount); battle.add_log(f"💖 {attacker['name']}이(가) {target['name']}의 체력을 {heal_amount}만큼 회복!")
            elif skill_number == 2: target.setdefault('effects', {})['mobility_modifier'] = 1; battle.add_log(f"🍃 {attacker['name']}이(가) {target['name']}의 다음 턴 이동력을 1 증가!")
            else: return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)


        elif advanced_class == "파이오니어":
            distance = battle.get_distance(attacker['pos'], target['pos'])
            
            if skill_number == 1: # 레벨*2만큼 체력 감소 후, 크리티컬 80% 원거리 공격
                if not (2 <= distance <= 3): return await ctx.send("❌ 원거리 공격 사거리가 아닙니다.")
                
                self_damage = attacker['level'] * 2
                attacker['current_hp'] = max(1, attacker['current_hp'] - self_damage)
                battle.add_log(f"🩸 {attacker['name']}이(가) 체력을 {self_damage} 소모합니다!")

                base_damage = attacker['mental'] + random.randint(0, attacker['physical'])
                attacker.setdefault('effects', {})['skill_crit_chance'] = 0.8


            elif skill_number == 2: # 광역 공격 / 단일 공격
                # 1. 사거리 확인
                if not (2 <= distance <= 3): return await ctx.send("❌ 원거리 스킬 사거리가 아닙니다.")
                
                base_damage = attacker['mental'] + random.randint(0, attacker['physical'])

                # 2. 전투 타입에 따라 로직 분기
                if battle.battle_type == "pvp_team": # 팀 대결일 경우 (기존 광역 로직)
                    enemy_team_ids = battle.team_b_ids if attacker['id'] in battle.team_a_ids else battle.team_a_ids
                    hit_enemies = []
                    for enemy_id in enemy_team_ids:
                        enemy_target = battle.players[enemy_id]
                        distance_to_enemy = battle.get_distance(attacker['pos'], enemy_target['pos'])
                        if 2 <= distance_to_enemy <= 3:
                            await self._apply_damage(battle, attacker, enemy_target, base_damage)
                            hit_enemies.append(enemy_target['name'])
                    
                    if not hit_enemies: return await ctx.send("사거리 안에 있는 적이 없습니다.")
                    battle.add_log(f"☄️ {attacker['name']}이(가) **{', '.join(hit_enemies)}**에게 광역 피해!")
                    
                    if random.random() < 0.20:
                        # 자신을 제외한 팀원 목록을 가져옵니다.
                        teammate_ids = [pid for pid in (battle.team_a_ids if attacker['id'] in battle.team_a_ids else battle.team_b_ids) if pid != attacker['id']]
                        if teammate_ids:
                            hit_teammate_id = random.choice(teammate_ids)
                            teammate_target = battle.players[hit_teammate_id]
                            
                            battle.add_log(f"마력에 팀원 **{teammate_target['name']}**이(가) 휘말립니다!")
                            # 팀원에게도 동일한 규칙으로 데미지 적용
                            await self._apply_damage(battle, attacker, teammate_target, base_damage)
                
                else: # 1:1 대결일 경우 (단순 원거리 공격)
                    return await ctx.send("이 스킬은 팀 대결에서만 사용할 수 있습니다.")
            else: 
                return await ctx.send("잘못된 스킬 번호입니다.")
            



        elif advanced_class == "헌터":
            if skill_number == 1: # 크리티컬 50%의 근거리 공격
                if battle.get_distance(attacker['pos'], target['pos']) != 1: 
                    return await ctx.send("❌ 근거리 공격 사거리가 아닙니다.")
                
                # 1. 기본 데미지만 계산
                base_damage = attacker['physical'] + random.randint(0, attacker['mental'])
                
                attacker.setdefault('effects', {})['skill_crit_chance'] = 0.5
                await self._apply_damage(battle, attacker, target, base_damage)



            elif skill_number == 2: # 사거리 무관 공격 + 방어 초기화
                # 사거리 확인 로직이 없는 것이 정상입니다.
                
                # 1. 기본 데미지 계산
                base_damage = attacker['mental'] + random.randint(0, attacker['physical'])
                
                # 2. 헬퍼 함수를 호출하여 모든 데미지 계산 및 적용
                await self._apply_damage(battle, attacker, target, base_damage)
                
                # 3. 방어도 초기화 및 추가 로그
                target['defense'] = 0
                battle.add_log(f"🛡️ {target['name']}의 방어도가 초기화되었습니다!")
            else: 
                return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)

        elif advanced_class == "조커":
            distance = battle.get_distance(attacker['pos'], target['pos'])
            advantages = {'Wit': 'Gut', 'Gut': 'Heart', 'Heart': 'Wit'}

            if skill_number == 1:
                # 1. 공격 타입 및 사거리 확인
                can_attack, attack_type = False, ""
                if distance == 1: can_attack, attack_type = True, "근거리"
                elif 2 <= distance <= 3: can_attack, attack_type = True, "원거리"
                if not can_attack: return await ctx.send("❌ 공격 사거리가 아닙니다.")

                # 2. 기본 데미지 계산 후 헬퍼 함수 호출
                base_damage = attacker['physical'] + random.randint(0, attacker['mental']) if attack_type == "근거리" else attacker['mental'] + random.randint(0, attacker['physical'])
                await self._apply_damage(battle, attacker, target, base_damage)

                # 3. 상성 우위 시 추가 데미지 적용
                if advantages.get(attacker['attribute']) == target.get('attribute'):
                    bonus_damage = target['level'] * 2
                    target['current_hp'] = max(0, target['current_hp'] - bonus_damage)
                    battle.add_log(f"🃏 조커의 속임수! 상성 우위로 **{bonus_damage}**의 추가 피해!")

            elif skill_number == 2:
                # 1. 상성 불리 확인
                if advantages.get(target.get('attribute')) == attacker.get('attribute'):
                    defense_gain = attacker['level'] * 4
                    attacker['defense'] += defense_gain
                    battle.add_log(f"🛡️ 상성 불리! **{attacker['name']}**이(가) 자신에게 방어도 **{defense_gain}**을 부여!")
                else:
                    battle.add_log(f"…{attacker['name']}이(가) 스킬을 사용했지만 아무 효과도 없었다.")
            else:
                return await ctx.send("잘못된 스킬 번호입니다.", delete_after=10)

        elif advanced_class == "그랜터":
            if skill_number == 1: # 다음 공격 2배 부여
                target.setdefault('effects', {})['next_attack_multiplier'] = 2.0
                battle.add_log(f"✨ {attacker['name']}이(가) {target['name']}에게 힘을 부여! 다음 공격을 크리티컬로!")
            elif skill_number == 2: # 2턴간 체력 회복
                target.setdefault('effects', {})['heal_over_time'] = {'amount': round(target['max_hp'] / 5), 'duration': 2}
                battle.add_log(f"💚 {attacker['name']}이(가) {target['name']}에게 지속 회복 효과를 부여!")
            else: return await ctx.send("잘못된 스킬 번호입니다.")






        attacker['special_cooldown'] = 2
        await battle.handle_action_cost(1)
        
        # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
        # 타겟이 쓰러졌는지 확인
        if target['current_hp'] <= 0:
            # 팀전일 경우에만 리타이어 헬퍼 호출
            if battle.battle_type == "pvp_team":
                battle.handle_retirement(target)
                
                # 게임 종료 여부 확인
                if await battle.check_game_over(): 
                    del self.active_battles[ctx.channel.id]
                else: 
                    await battle.display_board() # 게임이 안 끝났으면 업데이트된 맵 표시
            
            # 1:1 대결일 경우 (기존 방식)
            else: 
                battle.add_log(f"☠️ {target['name']}이(가) 쓰러졌습니다!")
                await battle.end_battle(ctx.author, f"{target['name']}이(가) 스킬을 받고 쓰러졌습니다!")
                del self.active_battles[ctx.channel.id]
 
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
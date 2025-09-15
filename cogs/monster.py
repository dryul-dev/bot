# cogs/monster.py

import discord
from discord.ext import commands
import json
import os
import random
import asyncio

# 데이터 로딩/저장 함수 (다른 Cog와 동일)
def load_data():
    if not os.path.exists("player_data.json"): return {}
    with open("player_data.json", 'r', encoding='utf-8') as f: return json.load(f)
def save_data(data):
    with open("player_data.json", 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

# 몬스터 기본 정보
MONSTER_DATA = {
    "슬라임": {
        "attribute": "Heart",
        "base_hp_multiplier": 3.5, # 체력 계수
        "base_ap_multiplier": 0.2, # 공격력 계수
        "drops": [{"name": "끈적한 점액", "chance": 0.8}, {"name": "슬라임의 핵", "chance": 0.2}]
    },
    "고블린": {
        "attribute": "Gut",
        "base_hp_multiplier": 4.0,
        "base_ap_multiplier": 0.25,
        "drops": [{"name": "끈적한 콧물", "chance": 0.5}, {"name": "금가루", "chance": 0.7}]
    },
    "임프": {
        "attribute": "Wit",
        "base_hp_multiplier": 3.0,
        "base_ap_multiplier": 0.3,
        "drops": [{"name": "작은 날개", "chance": 0.6}, {"name": "마력의 결정", "chance": 0.4}]
    }
}

# PvE 전투 관리 클래스
class PveBattle:
    def __init__(self, channel, player_user, active_battles_ref):
        self.channel = channel
        self.player_user = player_user
        self.active_battles = active_battles_ref # active_battles 딕셔너리 참조
        self.turn_timer = None # 타이머 변수 추가

        
        all_data = load_data()
        player_id_str = str(player_user.id)
        player_data = all_data[player_id_str]
        
        # 플레이어 스탯 설정
        level = 1 + ((player_data['mental'] + player_data['physical']) // 5)
        self.player_stats = {
            "id": player_user.id, "name": player_data['name'], "class": player_data['class'],
            "advanced_class": player_data.get("advanced_class"), "attribute": player_data.get("attribute"),
            "mental": player_data['mental'], "physical": player_data['physical'], "level": level,
            "hp": max(1, level * 10 + player_data['physical']), "current_hp": max(1, level * 10 + player_data['physical']),
            "color": int(player_data['color'][1:], 16), "special_cooldown": 0
        }

        # 몬스터 선택 및 스탯 동적 생성
        monster_name = random.choice(list(MONSTER_DATA.keys()))
        monster_template = MONSTER_DATA[monster_name]
        
        # 밸런싱 로직
        avg_player_damage = (self.player_stats['physical'] + self.player_stats['mental']) / 2 + self.player_stats['level']
        monster_hp = round(avg_player_damage * random.uniform(3.5, 5.0)) # 3~5방
        monster_ap = round(self.player_stats['hp'] / random.uniform(4.5, 6.0)) # 4~6방

        self.monster_stats = {
            "name": monster_name, "level": level, "attribute": monster_template['attribute'],
            "hp": monster_hp, "current_hp": monster_hp, "ap": monster_ap,
            "drops": monster_template['drops']
        }
        self.current_turn = "player"


    async def start_turn_timer(self):
        """턴 제한 시간 타이머를 시작/재시작합니다."""
        if self.turn_timer:
            self.turn_timer.cancel()
        self.turn_timer = asyncio.create_task(self.timeout_task())

    async def timeout_task(self):
        """5분이 지나면 타임아웃으로 패배 처리합니다."""
        try:
            await asyncio.sleep(300) # 5분
            await self.channel.send("사냥 시간이 너무 오래 걸려 집중력을 잃었습니다...")
            await self.end_battle(win=False)
        except asyncio.CancelledError:
            pass

    async def end_battle(self, win):
        if self.channel.id in self.active_battles:
            del self.active_battles[self.channel.id]

        if win:
            # 보상 획득 로직
            gold_won = self.monster_stats['level'] * random.randint(5, 10)
            materials_won = [item['name'] for item in self.monster_stats['drops'] if random.random() < item['chance']]
            
            # 데이터 저장
            all_data = load_data()
            player_data = all_data.get(str(self.player_user.id))
            if player_data:
                player_data['gold'] = player_data.get('gold', 0) + gold_won
                pve_inventory = player_data.get('pve_inventory', [])
                pve_inventory.extend(materials_won)
                player_data['pve_inventory'] = pve_inventory
                save_data(all_data)

            embed = discord.Embed(title="🎉 사냥 성공!", description=f"**{self.monster_stats['name']}**을(를) 처치했습니다!", color=discord.Color.gold())
            embed.add_field(name="획득 골드", value=f"`{gold_won}` G", inline=True)
            if materials_won:
                embed.add_field(name="획득 재료", value="\n".join(f"- {mat}" for mat in materials_won), inline=True)
            await self.channel.send(embed=embed)
        else:
            await self.channel.send("사냥에 실패했다...일단 보건실에 가자.")
    async def monster_turn(self):
        """몬스터의 턴을 진행합니다."""
        await self.channel.send("--- 몬스터의 턴 ---")
        await asyncio.sleep(1.5) # 긴장감 연출을 위한 딜레이

        monster = self.monster_stats
        player = self.player_stats
        
        # 행동 확률 결정
        action_roll = random.random()

        # 1. 일반 공격 (60% 확률)
        if action_roll < 0.6:
            damage = max(1, monster['ap'] + random.randint(-monster['level'], monster['level']))
            # 플레이어의 방어력(PvE용)이 있다면 적용
            final_damage = max(1, damage - player.get('pve_defense', 0))
            player['current_hp'] = max(0, player['current_hp'] - final_damage)
            
            log_message = f"👹 **{monster['name']}**의 공격! **{player['name']}**에게 **{final_damage}**의 피해를 입혔습니다."
            if player.get('pve_defense', 0) > 0:
                log_message += f" (방어함)"
                player['pve_defense'] = 0 # 방어력은 1회성으로 초기화

        # 2. 방어 (30% 확률)
        elif action_roll < 0.9:
            defense_gain = round(monster['hp'] * 0.2) # 최대 체력의 20%
            monster['defense'] = monster.get('defense', 0) + defense_gain
            log_message = f"🛡️ **{monster['name']}**이(가) 방어 태세를 갖춥니다! (방어도 +{defense_gain})"

        # 3. 강한 공격 (10% 확률)
        else:
            damage = max(1, monster['ap'] + random.randint(-monster['level'], monster['level'])) * 2
            final_damage = max(1, damage - player.get('pve_defense', 0))
            player['current_hp'] = max(0, player['current_hp'] - final_damage)
            
            log_message = f"💥 **{monster['name']}**의 강한 공격! **{player['name']}**에게 **{final_damage}**의 치명적인 피해를 입혔습니다!"
            if player.get('pve_defense', 0) > 0:
                player['pve_defense'] = 0

        # 결과 알림 및 다음 턴 준비
        embed = discord.Embed(description=log_message, color=0xDC143C)
        await self.channel.send(embed=embed)
        await asyncio.sleep(2)

        if player['current_hp'] <= 0:
            await self.end_battle(win=False)
            return

        # 플레이어 턴으로 전환 및 타이머 재시작
        self.current_turn = "player"
        embed = discord.Embed(title="▶️ 당신의 턴입니다", color=player['color'])
        embed.add_field(name=f"{player['name']}", value=f"HP: {player['current_hp']}/{player['hp']}", inline=True)
        embed.add_field(name=f"{monster['name']}", value=f"HP: {monster['current_hp']}/{monster['hp']}", inline=True)
        await self.channel.send(embed=embed)
        
        await self.start_turn_timer()

# Monster Cog 클래스
class MonsterCog(commands.Cog):
    def __init__(self, bot, active_battles_ref):
        self.bot = bot
        self.active_battles = active_battles_ref

    @commands.command(name="사냥")
    async def hunt(self, ctx):
        if ctx.channel.id in self.active_battles:
            return await ctx.send("이 채널에서는 이미 다른 활동(전투, 사냥 등)이 진행중입니다.")

        battle = PveBattle(ctx.channel, ctx.author, self.active_battles)
        self.active_battles[ctx.channel.id] = battle

        embed = discord.Embed(title=f"몬스터 출현! - {battle.monster_stats['name']} (Lv.{battle.monster_stats['level']})", color=0xDC143C)
        embed.add_field(name=f"{battle.player_stats['name']} (Lv.{battle.player_stats['level']})", value=f"HP: {battle.player_stats['current_hp']}/{battle.player_stats['hp']}", inline=True)
        embed.add_field(name=f"{battle.monster_stats['name']}", value=f"HP: {battle.monster_stats['current_hp']}/{battle.monster_stats['hp']}", inline=True)
        embed.set_footer(text="당신의 턴입니다. (`!공격`, `!스킬 1`, `!아이템`, `!도망`)")
        await ctx.send(embed=embed)

# 봇에 Cog를 추가하기 위한 필수 함수
async def setup(bot):
    # active_battles 딕셔너리를 공유하기 위해 main.py에서 전달받도록 수정
    await bot.add_cog(MonsterCog(bot, bot.active_battles))
# cogs/monster.py

import discord
from discord.ext import commands
import json
import os
import random
import asyncio

def load_data():
    if not os.path.exists("player_data.json"): return {}
    with open("player_data.json", 'r', encoding='utf-8') as f: return json.load(f)
def save_data(data):
    with open("player_data.json", 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

MONSTER_DATA = {
    "슬라임": { "attribute": "Heart", "drops": [{"name": "끈적한 점액", "chance": 0.8}, {"name": "슬라임의 핵", "chance": 0.2}] },
    "고블린": { "attribute": "Gut", "drops": [{"name": "낡은 단검", "chance": 0.5}, {"name": "가죽 조각", "chance": 0.5}] },
    "임프": { "attribute": "Wit", "drops": [{"name": "작은 날개", "chance": 0.6}, {"name": "마력의 가루", "chance": 0.4}] }
}

class PveBattle:
    def __init__(self, channel, player_user, active_battles_ref):

        
        self.channel = channel
        self.player_user = player_user
        self.active_battles = active_battles_ref
        self.turn_timer = None
        self.battle_type = "pve"
        self.battle_log = ["사냥을 시작합니다!"]


        
        all_data = load_data()
        player_data = all_data.get(str(player_user.id), {})
        
        level = 1 + ((player_data.get('mental', 0) + player_data.get('physical', 0)) // 5)
        player_hp = max(1, level * 10 + player_data.get('physical', 0))
        
        self.player_stats = {
            "id": player_user.id, "name": player_data.get('name', 'Unknown'), 
            "class": player_data.get('class'), "advanced_class": player_data.get("advanced_class"), 
            "attribute": player_data.get("attribute"), "mental": player_data.get('mental', 0), 
            "physical": player_data.get('physical', 0), "level": level, "hp": player_hp, 
            "current_hp": player_hp, "pve_defense": 0,
            "color": int(player_data.get('color', '#FFFFFF')[1:], 16), "special_cooldown": 0
        }

        monster_name = random.choice(list(MONSTER_DATA.keys()))
        monster_template = MONSTER_DATA[monster_name]
        
        avg_player_damage = (self.player_stats['physical'] + self.player_stats['mental']) / 2 + self.player_stats['level']
        monster_hp = round(max(10, avg_player_damage * random.uniform(2.5, 3.5)))

        # 공격력: 플레이어 체력을 나누는 값을 늘려서, 몬스터의 공격력을 낮춤
        monster_ap = round(max(2, self.player_stats['hp'] / random.uniform(6.0, 8.0)))

        self.monster_stats = {
            "name": monster_name, "level": level, "attribute": monster_template['attribute'], "defense": 0,
            "hp": monster_hp, "current_hp": monster_hp, "ap": monster_ap,
            "drops": monster_template['drops']
        }
        self.current_turn = "player"
    def add_log(self, message):
        self.battle_log.append(message)
        if len(self.battle_log) > 5:
            self.battle_log.pop(0)
    async def start_turn_timer(self):
        if self.turn_timer: self.turn_timer.cancel()
        self.turn_timer = asyncio.create_task(self.timeout_task())
    async def timeout_task(self):
        try:
            await asyncio.sleep(300); await self.end_battle(win=False, reason="사냥 시간이 너무 오래 걸려 집중력을 잃었습니다...")
        except asyncio.CancelledError: pass
    async def end_battle(self, win, reason=""):
        if self.turn_timer: self.turn_timer.cancel()
        if self.channel.id in self.active_battles: del self.active_battles[self.channel.id]
        if win:
            gold_won = self.monster_stats['level'] * random.randint(5, 10); 
            materials_won = [item['name'] for item in self.monster_stats['drops'] if random.random() < item['chance']]
            all_data = load_data(); 
            player_data = all_data.get(str(self.player_user.id))
            if player_data:
                # 데이터 업데이트
                player_data['gold'] = player_data.get('gold', 0) + gold_won
                pve_inventory = player_data.get('pve_inventory', {})
                for material in materials_won:
                    # 보관함에 자리가 있을 때만 재료 추가
                    if len(pve_inventory) < 10 or material in pve_inventory:
                        current_amount = pve_inventory.get(material, 0)
                        pve_inventory[material] = min(20, current_amount + 1) # 최대 20개 제한
                
                player_data['pve_inventory'] = pve_inventory
                save_data(all_data)

                # 결과 메시지 생성 및 전송
                embed = discord.Embed(title="🎉 사냥 성공!", description=f"**{self.monster_stats['name']}**을(를) 처치했습니다!", color=discord.Color.gold())
                embed.add_field(name="획득 골드", value=f"`{gold_won}` G", inline=True)
                if materials_won:
                    embed.add_field(name="획득 재료", value="\n".join(f"- {mat}" for mat in materials_won), inline=True)
                await self.channel.send(embed=embed)
        else: await self.channel.send(reason if reason else "사냥에 실패했습니다. 보건실에 갑시다.")
# cogs/monster.py 의 PveBattle 클래스 내부

    async def monster_turn(self):
        """몬스터의 턴을 진행하고, 결과를 하나의 Embed로 통합하여 보여줍니다."""
        monster = self.monster_stats
        player = self.player_stats
        
        action_roll = random.random()
        log_message = "" # 몬스터가 무슨 행동을 했는지 기록

        # 1. 몬스터 행동 결정 및 데미지/방어 계산
        if action_roll < 0.6: # 일반 공격
            damage = max(1, monster['ap'] + random.randint(-monster['level'], monster['level']))
            final_damage = max(1, damage - player.get('pve_defense', 0))
            player['current_hp'] = max(0, player['current_hp'] - final_damage)
            log_message = f"👹 **{monster['name']}**의 공격! **{player['name']}**에게 **{final_damage}**의 피해!"
            if player.get('pve_defense', 0) > 0: log_message += " (방어함)"; player['pve_defense'] = 0
        
        elif action_roll < 0.9: # 방어
            defense_gain = round(monster['hp'] * 0.2)
            monster['defense'] += defense_gain
            log_message = f"🛡️ **{monster['name']}**이(가) 방어 태세를 갖춥니다! (방어도 +{defense_gain})"
        
        else: # 강한 공격
            damage = max(1, monster['ap'] + random.randint(-monster['level'], monster['level'])) * 2
            final_damage = max(1, damage - player.get('pve_defense', 0))
            player['current_hp'] = max(0, player['current_hp'] - final_damage)
            log_message = f"💥 **{monster['name']}**의 강한 공격! **{player['name']}에게 {final_damage}**의 치명적인 피해!"
            if player.get('pve_defense', 0) > 0: player['pve_defense'] = 0

        # 2. 플레이어가 쓰러졌는지 확인
        if player['current_hp'] <= 0:
            await self.channel.send(embed=discord.Embed(description=log_message, color=0xDC143C))
            await asyncio.sleep(1)
            await self.end_battle(win=False, reason=f"{monster['name']}의 공격에 쓰러졌습니다...")
            return

        # 3. 모든 결과를 하나의 Embed로 통합하여 전송
        self.current_turn = "player"
        embed = discord.Embed(title="몬스터의 턴 결과", description=log_message, color=player['color'])
        embed.add_field(name=f"{player['name']}", value=f"HP: {player['current_hp']}/{player['hp']}", inline=True)
        embed.add_field(name=f"{monster['name']}", value=f"HP: {monster['current_hp']}/{monster['hp']}", inline=True)
        embed.set_footer(text="▶️ 당신의 턴입니다.")
        await self.channel.send(embed=embed)
        
        await self.start_turn_timer()
class MonsterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_battles = bot.active_battles

# cogs/monster.py 의 MonsterCog 클래스 내부에 추가

    @commands.command(name="루트")
    async def loot(self, ctx):
        """자신이 보유한 골드와 PvE 재료를 확인합니다."""
        all_data = load_data()
        player_data = all_data.get(str(ctx.author.id))

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")

        gold = player_data.get("gold", 0)
        pve_inventory = player_data.get("pve_inventory", {})

        # Embed 생성
        embed = discord.Embed(
            title=f"💰 {player_data['name']}의 전리품",
            color=int(player_data.get('color', '#FFFFFF')[1:], 16)
        )
        embed.add_field(name="보유 골드", value=f"`{gold}` G", inline=False)
        
        # 재료 목록 생성
        if not pve_inventory:
            loot_list = "아직 재료가 없습니다."
        else:
            # pve_inventory를 딕셔너리로 가정하고 처리
            loot_list = "\n".join(f"- {name}: `{count}`/20개" for name, count in pve_inventory.items())
        
        embed.add_field(
            name=f"보유 재료 ({len(pve_inventory)}/10 종류)",
            value=loot_list,
            inline=False
        )
        embed.set_footer(text="재료 보관함이 가득 차면, 시장에서 판매해야 합니다.")
        await ctx.send(embed=embed)

        # cogs/monster.py 의 MonsterCog 클래스 내부에 추가

    @commands.command(name="아이템")
    async def use_pve_item(self, ctx, *, item_name: str):
        """사냥 중에 전투용 아이템을 사용합니다."""
        battle = self.active_battles.get(ctx.channel.id)
        
        # 1. PvE 전투 중인지, 본인의 턴이 맞는지 확인
        if not isinstance(battle, PveBattle) or battle.current_turn != "player" or ctx.author.id != battle.player_user.id:
            return await ctx.send("사냥 중인 자신의 턴에만 사용할 수 있습니다.")

        all_data = load_data()
        player_id_str = str(ctx.author.id)
        player_data = all_data.get(player_id_str)
        pve_inventory = player_data.get("pve_inventory", {})

        # 2. 아이템 보유 여부 확인
        if item_name not in pve_inventory or pve_inventory[item_name] <= 0:
            return await ctx.send(f"'{item_name}' 아이템을 가지고 있지 않습니다.")

        player = battle.player_stats
        
        # 3. 아이템 효과 적용 (나중에 아이템 종류에 따라 확장 가능)
        item_used = False
        if item_name == "하급 체력 포션": # 예시 아이템
            heal_amount = 50
            player['current_hp'] = min(player['hp'], player['current_hp'] + heal_amount)
            battle.add_log(f"🧪 {player['name']}이(가) 하급 체력 포션을 사용하여 체력을 {heal_amount} 회복했습니다.")
            item_used = True
        
        # 4. 아이템 사용 처리
        if item_used:
            pve_inventory[item_name] -= 1
            if pve_inventory[item_name] == 0:
                del pve_inventory[item_name]
            save_data(all_data)
            
            # 아이템 사용 후 상황판을 다시 보여줌 (턴은 소모하지 않음)
            embed = discord.Embed(title="아이템 사용", description=f"{player['name']}의 턴이 계속됩니다.", color=player['color'])
            embed.add_field(name=f"{player['name']}", value=f"HP: {player['current_hp']}/{player['hp']}", inline=True)
            embed.add_field(name=f"{battle.monster_stats['name']}", value=f"HP: {battle.monster_stats['current_hp']}/{battle.monster_stats['hp']}", inline=True)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"'{item_name}'은 전투 중에 사용할 수 없는 아이템입니다.")

# cogs/monster.py 의 MonsterCog 클래스 내부에 추가

    @commands.command(name="아이템가방")
    async def item_bag(self, ctx):
        """자신이 보유한 PvE 장비 및 소모품을 확인합니다."""
        all_data = load_data()
        player_id = str(ctx.author.id)
        player_data = all_data.get(player_id)

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")

        # pve_item_bag이 없을 경우를 대비해 기본값으로 빈 딕셔너리 설정
        pve_item_bag = player_data.get("pve_item_bag", {})
        
        # Embed 생성
        embed = discord.Embed(
            title=f"🎒 {player_data.get('name', ctx.author.display_name)}의 아이템 가방",
            description="사냥과 전투에 사용하는 장비와 소모품을 보관합니다.",
            color=int(player_data.get('color', '#FFFFFF')[1:], 16)
        )
        
        # 아이템 목록 생성
        if not pve_item_bag:
            item_list = "아직 아이템이 없습니다."
        else:
            # pve_item_bag은 {"아이템 이름": 개수} 형태의 딕셔너리
            item_list = "\n".join(f"- {name}: `{count}`개" for name, count in pve_item_bag.items())
        
        embed.add_field(
            name="보유 아이템",
            value=item_list,
            inline=False
        )
        await ctx.send(embed=embed)

    @commands.command(name="사냥")
    async def hunt(self, ctx):
        if ctx.channel.id in self.active_battles: return await ctx.send("이 채널에서는 이미 다른 활동이 진행중입니다.")
        battle = PveBattle(ctx.channel, ctx.author, self.active_battles); self.active_battles[ctx.channel.id] = battle
        embed = discord.Embed(title=f"몬스터 출현! - {battle.monster_stats['name']} (Lv.{battle.monster_stats['level']})", color=0xDC143C); embed.add_field(name=f"{battle.player_stats['name']} (Lv.{battle.player_stats['level']})", value=f"HP: {battle.player_stats['current_hp']}/{battle.player_stats['hp']}", inline=True); embed.add_field(name=f"{battle.monster_stats['name']}", value=f"HP: {battle.monster_stats['current_hp']}/{battle.monster_stats['hp']}", inline=True); embed.set_footer(text="당신의 턴입니다. (`!공격`, `!스킬 1`, `!도망`)"); await ctx.send(embed=embed); await battle.start_turn_timer()
        # cogs/monster.py 의 MonsterCog 클래스 내부

    @commands.command(name="도망")
    async def flee(self, ctx):
        """진행 중인 몬스터와의 전투에서 도망칩니다."""
        battle = self.active_battles.get(ctx.channel.id)
        
        # 현재 사냥 중인지, 본인의 턴이 맞는지 확인
        if not isinstance(battle, PveBattle) or battle.current_turn != "player" or ctx.author.id != battle.player_user.id:
            return

        # 50% 확률로 도망 성공
        if random.random() < 0.5:
            await battle.end_battle(win=False, reason=f"{ctx.author.display_name}이(가) 전투에서 성공적으로 도망쳤습니다!")
        else:
            await ctx.send("도망에 실패했다! 몬스터가 공격해온다!")
            await asyncio.sleep(1)
            await battle.monster_turn()


# cogs/growth.py의 fix_data_structure 함수 내부
    
    @commands.command(name="데이터점검")
    @commands.is_owner()
    async def fix_data_structure(self, ctx):
        await ctx.send("모든 유저 데이터 구조 점검 및 업데이트를 시작합니다...")
        
        all_data = load_data()
        updated_users = 0
        
        for player_id, player_data in all_data.items():
            updated = False
            
            # ... (기존 필드 추가 로직) ...

            # ▼▼▼ 여기가 추가된 부분입니다 ▼▼▼
            # pve_inventory가 리스트 형식일 경우 딕셔너리로 변환
            if 'pve_inventory' in player_data and isinstance(player_data['pve_inventory'], list):
                old_inventory_list = player_data['pve_inventory']
                new_inventory_dict = {}
                for item in old_inventory_list:
                    # 각 아이템의 개수를 세어서 딕셔너리에 저장
                    new_inventory_dict[item] = new_inventory_dict.get(item, 0) + 1
                
                player_data['pve_inventory'] = new_inventory_dict
                updated = True
            # ▲▲▲ 여기가 추가된 부분입니다 ▲▲▲
            if 'today_blessing' not in player_data:
                player_data.setdefault('today_blessing', None)
                updated = True
            if 'last_blessing_date' not in player_data:
                player_data.setdefault('last_blessing_date', None)
                updated = True

            if 'goals' not in player_data:
                player_data.setdefault('goals', [])
                updated = True
            if 'last_goal_date' not in player_data:
                player_data.setdefault('last_goal_date', None)
                updated = True

            if 'pve_item_bag' not in player_data:
                player_data.setdefault('pve_item_bag', {})
                updated = True
            # ... (임시 데이터 초기화 로직) ...

        save_data(all_data)
        await ctx.send(f"✅ 완료! 총 {len(all_data)}명의 유저 중 {updated_users}명의 데이터 구조를 업데이트했습니다.")  
        
async def setup(bot):
    await bot.add_cog(MonsterCog(bot))
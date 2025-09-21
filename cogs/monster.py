# cogs/monster.py

import discord
from discord.ext import commands
import json
import os
import random
import asyncio
from datetime import datetime

def load_data():
    if not os.path.exists("player_data.json"): return {}
    with open("player_data.json", 'r', encoding='utf-8') as f: return json.load(f)
def save_data(data):
    with open("player_data.json", 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)


# cogs/monster.py 상단

HUNTING_GROUNDS = {
    "마을 인근": {
        "monsters": ["슬라임", "고블린", "임프"],
        "difficulty": {
            "hp_mult": [2.5, 3.5],
            "ap_div": [6.0, 8.0],
            "min_hp": 15,
            "min_ap": 3
        }
    },
    "자작나무 숲": {
        "monsters": ["성난 늑대", "오염된 정령"],
        "difficulty": {
            "hp_mult": [3.0, 4.5],
            "ap_div": [5.0, 7.0],
            "min_hp": 20,
            "min_ap": 5
        }
    }
    # 나중에 새로운 사냥터를 추가할 때 이 형식에 맞춰 추가하기만 하면 됩니다.
}

                    # 드랍 확률이 낮은 재료부터 작성해야 오류가 안 남!!
MONSTER_DATA = {
    "슬라임": { "attribute": "Heart", "drops": [{"name": "슬라임의 핵", "chance": 0.2}, {"name": "끈적한 점액", "chance": 0.8}] },
    "고블린": { "attribute": "Gut", "drops": [{"name": "낡은 단검", "chance": 0.4}, {"name": "가죽 조각", "chance": 0.6}] },
    "임프": { "attribute": "Wit", "drops": [{"name": "마력의 가루", "chance": 0.3}, {"name": "작은 날개", "chance": 0.7}] },
    
    # --- 신규 몬스터 (자작나무 숲) ---
    "성난 늑대": { "attribute": "Gut", "drops": [{"name": "늑대 송곳니", "chance": 0.4}, {"name": "질긴 가죽", "chance": 0.6}] },
    "오염된 정령": { "attribute": "Wit", "drops": [{"name": "정령의 파편", "chance": 0.3}, {"name": "정령의 마력", "chance": 0.7}] }
}


CRAFTING_RECIPES = {
    # 레시피의 키는 재료 이름들을 알파벳 순으로 정렬한 튜플입니다.
    tuple(sorted(("끈적한 점액", "끈적한 점액"))): "하급 체력 포션",
    tuple(sorted(("가죽 조각", "슬라임의 핵"))): "하급 폭탄",
    tuple(sorted(("낡은 단검", "작은 날개"))): "하급 수리검",
    tuple(sorted(("가죽 조각", "마력의 가루"))):"가죽 장갑",
    tuple(sorted(("질긴 가죽", "정령의 마력"))): "가죽 갑옷"
}

# 시장에서 거래되는 아이템 정보 (구매가/판매가)
MARKET_ITEMS = {
    "하급 체력 포션": {"buy": 20, "sell": 12},
    "하급 폭탄": {"buy": 30, "sell": 18},
    "하급 수리검": {"buy": 12, "sell": 8},
    "가죽 장갑": {"buy": 30, "sell": 22},
    "가죽 갑옷": {"buy": 60, "sell": 45}

}

EQUIPMENT_EFFECTS = {
    "가죽 장갑": {"final_damage_bonus": 1},
    "가죽 갑옷": {"final_damage_bonus": 2}
}

class PveBattle:
    def __init__(self, channel, player_user, active_battles_ref, hunting_ground_name, monster_name):
        self.channel = channel; self.player_user = player_user; self.active_battles = active_battles_ref; self.turn_timer = None; self.battle_type = "pve"; self.battle_log = ["사냥을 시작합니다!"]
        player_data = load_data()[str(player_user.id)]
        level = 1 + ((player_data['mental'] + player_data['physical']) // 5); player_hp = max(1, level * 10 + player_data['physical'])
        equipped_gear = player_data.get("equipped_gear", []); gear_damage_bonus = sum(EQUIPMENT_EFFECTS.get(item, {}).get("final_damage_bonus", 0) for item in equipped_gear)

        
        self.player_stats = { "id": player_user.id, "name": player_data['name'], "class": player_data['class'], "advanced_class": player_data.get("advanced_class"), "attribute": player_data.get("attribute"), "mental": player_data['mental'], "physical": player_data['physical'], "level": level, "hp": player_hp, "current_hp": player_hp, "pve_defense": 0, "color": int(player_data.get('color', '#FFFFFF')[1:], 16), "special_cooldown": 0, "effects": {}, "gear_damage_bonus": gear_damage_bonus }
        monster_template = MONSTER_DATA[monster_name]; difficulty = HUNTING_GROUNDS[hunting_ground_name]["difficulty"]
        avg_player_damage = (self.player_stats['physical'] + self.player_stats['mental']) / 2 + self.player_stats['level']
        monster_hp = round(max(difficulty["min_hp"], avg_player_damage * random.uniform(*difficulty["hp_mult"]))); monster_ap = round(max(difficulty["min_ap"], self.player_stats['hp'] / random.uniform(*difficulty["ap_div"])))
        self.monster_stats = { "name": monster_name, "level": level, "attribute": monster_template['attribute'], "defense": 0, "hp": monster_hp, "current_hp": monster_hp, "ap": monster_ap, "drops": monster_template['drops'] }
        self.current_turn = "player"

    def add_log(self, message):
        self.battle_log.append(message)
        if len(self.battle_log) > 5: self.battle_log.pop(0)

    async def start_turn_timer(self):
        if self.turn_timer: self.turn_timer.cancel()
        self.turn_timer = asyncio.create_task(self.timeout_task())

    async def timeout_task(self):
        try:
            await asyncio.sleep(300)
            await self.end_battle(win=False, reason="사냥 시간이 너무 오래 걸려 집중력을 잃었습니다...")
        except asyncio.CancelledError: pass

    async def end_battle(self, win, reason=""):
        if self.turn_timer: self.turn_timer.cancel()
        if self.channel.id in self.active_battles: del self.active_battles[self.channel.id]
        if win:
            gold_won = self.monster_stats['level'] * random.randint(5, 10); materials_won = [item['name'] for item in self.monster_stats['drops'] if random.random() < item['chance']]
            all_data = load_data(); player_data = all_data.get(str(self.player_user.id))
            if player_data:
                player_data['gold'] = player_data.get('gold', 0) + gold_won; pve_inventory = player_data.get('pve_inventory', {});
                for material in materials_won:
                    if len(pve_inventory) < 10 or material in pve_inventory: pve_inventory[material] = min(20, pve_inventory.get(material, 0) + 1)
                player_data['pve_inventory'] = pve_inventory; save_data(all_data)
            embed = discord.Embed(title="🎉 사냥 성공!", description=f"**{self.monster_stats['name']}**을(를) 처치했습니다!", color=discord.Color.gold()); embed.add_field(name="획득 골드", value=f"`{gold_won}` G", inline=True)
            if materials_won: embed.add_field(name="획득 재료", value="\n".join(f"- {mat}" for mat in materials_won), inline=True)
            await self.channel.send(embed=embed)
        else: await self.channel.send(reason if reason else "사냥에 실패했다...일단 보건실에 가자.")


    async def monster_turn(self):
        monster = self.monster_stats
        player = self.player_stats
        
        action_roll = random.random()
        log_message = ""
        initial_defense = player.get('pve_defense', 0)

        # ▼▼▼ is_strong_attack 변수를 여기서 선언합니다. ▼▼▼
        is_strong_attack = (action_roll >= 0.9)
        
        # [행동 1: 방어 (30%)]
        if 0.6 <= action_roll < 0.9:
            defense_gain = round(monster['hp'] * 0.2)
            monster['defense'] += defense_gain
            log_message = f"🛡️ **{monster['name']}**이(가) 방어 태세를 갖춥니다! (방어도 +{defense_gain})"
        
        # [행동 2: 공격 (일반 60%, 강한 공격 10%)]
        else:
            multiplier = 2.0 if is_strong_attack else 1.0
            damage = max(1, monster['ap'] + random.randint(-monster['level'], monster['level'])) * multiplier
            
            defense_consumed = min(initial_defense, damage)
            final_damage = max(0, damage - initial_defense)
            player['pve_defense'] = initial_defense - defense_consumed
            
            player['current_hp'] = max(0, player['current_hp'] - final_damage)
            
            if is_strong_attack:
                log_message = f"💥 **{monster['name']}**의 강한 공격! **{player['name']}**에게 **{final_damage}**의 치명적인 피해!"
            else:
                log_message = f"👹 **{monster['name']}**의 공격! **{player['name']}**에게 **{final_damage}**의 피해!"

            if defense_consumed > 0:
                log_message += f" (방어도 {defense_consumed} 흡수)"

        # 2. 플레이어가 쓰러졌는지 확인
        if player['current_hp'] <= 0:
            await self.channel.send(embed=discord.Embed(description=log_message, color=0xDC143C))
            await asyncio.sleep(1)
            await self.end_battle(win=False, reason=f"{monster['name']}의 공격에 쓰러졌습니다...")
            return

        # 3. 플레이어 턴으로 전환 및 결과 통합 메시지 전송
        if player.get('special_cooldown', 0) > 0:
            player['special_cooldown'] -= 1
        
        self.current_turn = "player"
        embed = discord.Embed(title="몬스터의 턴 결과", description=log_message, color=player['color'])
        embed.add_field(name=f"{player['name']}", value=f"HP: {player['current_hp']}/{player['hp']}", inline=True)
        embed.add_field(name=f"{monster['name']}", value=f"HP: {monster['current_hp']}/{monster['hp']}", inline=True)
        embed.set_footer(text="▶️ 당신의 턴입니다.")
        await self.channel.send(embed=embed)
        
        await self.start_turn_timer()

class MonsterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot; self.active_battles = bot.active_battles

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

    @commands.command(name="아이템")
    async def use_pve_item(self, ctx, *, item_name: str):
        """사냥 중에 전투용 아이템을 사용합니다."""
        battle = self.active_battles.get(ctx.channel.id)
        
        if not isinstance(battle, PveBattle) or battle.current_turn != "player" or ctx.author.id != battle.player_user.id:
            return await ctx.send("사냥 중인 자신의 턴에만 사용할 수 있습니다.")

        all_data = load_data()
        player_data = all_data.get(str(ctx.author.id))
        pve_item_bag = player_data.get("pve_item_bag", {})

        if item_name not in pve_item_bag or pve_item_bag[item_name] <= 0:
            return await ctx.send(f"'{item_name}' 아이템을 가지고 있지 않습니다.")

        player = battle.player_stats
        monster = battle.monster_stats
        item_used = False
        
        # ▼▼▼ 여기가 수정/추가된 부분입니다 ▼▼▼
        if item_name == "하급 체력 포션":
            heal_amount = 5
            player['current_hp'] = min(player['hp'], player['current_hp'] + heal_amount)
            battle.add_log(f"🧪 {player['name']}이(가) {item_name}을(를) 사용하여 체력을 {heal_amount} 회복했습니다.")
            item_used = True

        elif item_name == "하급 폭탄":
            damage = 10
            monster['current_hp'] = max(0, monster['current_hp'] - damage)
            battle.add_log(f"💣 {player['name']}이(가) {item_name}을(를) 사용하여 몬스터에게 **{damage}**의 피해를 입혔습니다!")
            item_used = True

        elif item_name == "하급 수리검":
            damage = 5
            monster['current_hp'] = max(0, monster['current_hp'] - damage)
            battle.add_log(f"💨 {player['name']}이(가) {item_name}을(를) 던져 몬스터에게 **{damage}**의 피해를 입혔습니다!")
            item_used = True
        # ▲▲▲ 여기가 수정/추가된 부분입니다 ▲▲▲
        
        if item_used:
            # 아이템 소모
            pve_item_bag[item_name] -= 1
            if pve_item_bag[item_name] == 0:
                del pve_item_bag[item_name]
            save_data(all_data)
            
            # 몬스터가 죽었는지 확인
            if monster['current_hp'] <= 0:
                await battle.end_battle(win=True)
                return

            # 아이템 사용 후 상황판을 다시 보여줌 (턴은 소모하지 않음)
            embed = discord.Embed(title="아이템 사용", description=f"{player['name']}의 턴이 계속됩니다.", color=player['color'])
            embed.add_field(name=f"{player['name']}", value=f"HP: {player['current_hp']}/{player['hp']}", inline=True)
            embed.add_field(name=f"{monster['name']}", value=f"HP: {monster['current_hp']}/{monster['hp']}", inline=True)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"'{item_name}'은 전투 중에 사용할 수 없는 아이템입니다.")

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
            description="사냥에 사용하는 장비와 소모품을 보관합니다.",
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


    @commands.command(name="제작")
    async def craft_item(self, ctx, *, recipe_string: str):
        """두 개의 재료를 조합하여 아이템을 제작합니다. (!제작 재료1+재료2)"""
        
        # 1. '+'를 기준으로 재료 이름 분리
        try:
            material1, material2 = [m.strip() for m in recipe_string.split('+')]
        except ValueError:
            return await ctx.send("잘못된 형식입니다. `!제작 [재료1]+[재료2]` 형식으로 입력해주세요.")

        all_data = load_data()
        player_id = str(ctx.author.id)
        player_data = all_data.get(player_id)

        if not player_data or not player_data.get("registered"):
            return await ctx.send("먼저 `!등록`을 진행해주세요.")

        pve_inventory = player_data.get("pve_inventory", {})
        
        # 2. 재료 보유 여부 확인
        required = {material1: 1, material2: 1} if material1 != material2 else {material1: 2}
        for item, amount in required.items():
            if pve_inventory.get(item, 0) < amount:
                return await ctx.send(f"재료가 부족합니다: {item}")
        
        # 3. 레시피 확인
        recipe_key = tuple(sorted((material1, material2)))
        crafted_item = CRAFTING_RECIPES.get(recipe_key)

        if not crafted_item:
            return await ctx.send("...이 조합은 아닌 것 같다.")

        # 4. 재료 소모 및 아이템 획득
        for item, amount in required.items():
            pve_inventory[item] -= amount
            if pve_inventory[item] == 0:
                del pve_inventory[item]
        
        pve_item_bag = player_data.get("pve_item_bag", {})
        pve_item_bag[crafted_item] = pve_item_bag.get(crafted_item, 0) + 1
        
        save_data(all_data)
        await ctx.send(f"✨ **{crafted_item}** 제작에 성공했습니다!")


# cogs/monster.py 의 MonsterCog 클래스 내부에 추가

    @commands.command(name="시장")
    async def market(self, ctx):
        """시장에서 판매하는 PvE 아이템 목록을 보여줍니다."""
        embed = discord.Embed(
            title="🛠️ 시장",
            description="`!시장구매 [아이템]` 또는 `!시장판매 [아이템]`으로 거래할 수 있습니다.",
            color=0x00308F
        )
        
        item_list = []
        for name, prices in MARKET_ITEMS.items():
            item_list.append(f"- **{name}**: 구매가 `{prices['buy']}`G / 판매가 `{prices['sell']}`G")
            
        embed.add_field(name="거래 가능 품목", value="\n".join(item_list), inline=False)
        embed.set_footer(text="어서 와라, 하룻강아지들아!")
        await ctx.send(embed=embed)

    @commands.command(name="시장구매")
    async def market_buy(self, ctx, *, item_name: str):
        """시장에서 PvE 아이템을 구매합니다."""
        if item_name not in MARKET_ITEMS:
            return await ctx.send("시장에서 판매하지 않는 아이템입니다.")

        all_data = load_data()
        player_data = all_data.get(str(ctx.author.id))
        if not player_data: return await ctx.send("먼저 `!등록`을 진행해주세요.")

        item_info = MARKET_ITEMS[item_name]
        gold = player_data.get("gold", 0)

        if gold < item_info['buy']:
            return await ctx.send("골드가 부족합니다.")

        # 구매 확인
        await ctx.send(f"**{item_name}**을(를) `{item_info['buy']}`G에 구매하시겠습니까? (30초 안에 `예` 입력)")
        def check(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == '예'
        try:
            await self.bot.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            return await ctx.send("시간이 초과되어 구매가 취소되었습니다.")

        # 골드 차감 및 아이템 획득
        player_data['gold'] -= item_info['buy']
        pve_item_bag = player_data.get("pve_item_bag", {})
        pve_item_bag[item_name] = pve_item_bag.get(item_name, 0) + 1
        player_data["pve_item_bag"] = pve_item_bag
        
        save_data(all_data)
        await ctx.send(f"**{item_name}** 구매를 완료했습니다! (남은 골드: `{player_data['gold']}`G)")

    @commands.command(name="시장판매")
    async def market_sell(self, ctx, *, item_name: str):
        """보유한 PvE 아이템을 시장에 판매합니다."""
        if item_name not in MARKET_ITEMS:
            return await ctx.send("시장에서 취급하지 않는 아이템입니다.")

        all_data = load_data()
        player_data = all_data.get(str(ctx.author.id))
        if not player_data: return await ctx.send("먼저 `!등록`을 진행해주세요.")

        pve_item_bag = player_data.get("pve_item_bag", {})
        if pve_item_bag.get(item_name, 0) <= 0:
            return await ctx.send(f"'{item_name}' 아이템을 가지고 있지 않습니다.")

        item_info = MARKET_ITEMS[item_name]

        # 판매 확인
        await ctx.send(f"**{item_name}**을(를) `{item_info['sell']}`G에 판매하시겠습니까? (30초 안에 `예` 입력)")
        def check(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == '예'
        try:
            await self.bot.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            return await ctx.send("시간이 초과되어 판매가 취소되었습니다.")

        # 아이템 차감 및 골드 획득
        pve_item_bag[item_name] -= 1
        if pve_item_bag[item_name] == 0:
            del pve_item_bag[item_name]
        
        player_data['gold'] = player_data.get('gold', 0) + item_info['sell']
        
        save_data(all_data)
        await ctx.send(f"**{item_name}** 판매를 완료했습니다! (남은 골드: `{player_data['gold']}`G)")











# cogs/monster.py 의 MonsterCog 클래스 내부

    @commands.command(name="사냥")
    async def hunt(self, ctx, *, hunting_ground_name: str):
        """지정한 사냥터에서 몬스터 사냥을 시작합니다."""
        if ctx.channel.id in self.active_battles:
            return await ctx.send("이 채널에서는 이미 다른 활동이 진행중입니다.")

        # 1. 사용자가 입력한 이름과 코드에 정의된 이름 모두에서 공백을 제거하고 비교
        normalized_input = hunting_ground_name.replace(" ", "")
        found_ground_name = None
        for key in HUNTING_GROUNDS.keys():
            if key.replace(" ", "") == normalized_input:
                found_ground_name = key # 띄어쓰기가 포함된 '진짜' 이름을 저장
                break
        
        # 2. 일치하는 사냥터가 없는 경우, 목록을 보여주고 종료
        if not found_ground_name:
            valid_grounds = ", ".join(f"`{name}`" for name in HUNTING_GROUNDS.keys())
            return await ctx.send(f"존재하지 않는 사냥터입니다. (선택 가능: {valid_grounds})")

        # 3. 찾은 '진짜' 이름으로 몬스터 목록을 가져옴
        monster_list = HUNTING_GROUNDS[found_ground_name]["monsters"]
        monster_to_spawn = random.choice(monster_list)

        # 4. 전투 시작
        battle = PveBattle(ctx.channel, ctx.author, self.active_battles, found_ground_name, monster_to_spawn)
        self.active_battles[ctx.channel.id] = battle

        embed = discord.Embed(
            title=f"몬스터 출현! - {battle.monster_stats['name']} (Lv.{battle.monster_stats['level']})",
            description=f"**[{found_ground_name}]**에서 전투가 시작됩니다.",
            color=0xDC143C
        )
        embed.add_field(name=f"{battle.player_stats['name']} (Lv.{battle.player_stats['level']})", value=f"HP: {battle.player_stats['current_hp']}/{battle.player_stats['hp']}", inline=True)
        embed.add_field(name=f"{battle.monster_stats['name']}", value=f"HP: {battle.monster_stats['current_hp']}/{battle.monster_stats['hp']}", inline=True)
        embed.set_footer(text="당신의 턴입니다. (`!공격`, `!아이템 [아이템이름]`, `!도망`)")
        await ctx.send(embed=embed)
        await battle.start_turn_timer()

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







    @commands.command(name="장비")
    async def equipment_info(self, ctx):
        """현재 장착한 장비를 확인합니다."""
        all_data = load_data()
        player_data = all_data.get(str(ctx.author.id), {})
        equipped_gear = player_data.get("equipped_gear", [])

        embed = discord.Embed(
            title=f"🛠️ {player_data.get('name', ctx.author.display_name)}의 장비",
            color=int(player_data.get('color', '#FFFFFF')[1:], 16)
        )
        
        if not equipped_gear:
            embed.description = "장착한 장비가 없습니다."
        else:
            for item_name in equipped_gear:
                effect = EQUIPMENT_EFFECTS.get(item_name, {})
                effect_str = "효과 없음" # 기본값
                
                # 향후 다른 종류의 효과가 추가될 것을 대비한 구조
                if "final_damage_bonus" in effect:
                    effect_str = f"최종 데미지 +{effect['final_damage_bonus']}"
                
                embed.add_field(name=item_name, value=effect_str, inline=False)
        
        embed.set_footer(text=f"장착 슬롯: {len(equipped_gear)}/2")
        await ctx.send(embed=embed)



    @commands.command(name="장착")
    async def equip_item(self, ctx, *, item_name: str):
        """아이템 가방에 있는 장비를 장착합니다."""
        all_data = load_data()
        player_data = all_data.get(str(ctx.author.id), {})
        pve_item_bag = player_data.get("pve_item_bag", {})
        equipped_gear = player_data.get("equipped_gear", [])

        if item_name not in pve_item_bag or pve_item_bag[item_name] <= 0:
            return await ctx.send(f"'{item_name}' 아이템을 가지고 있지 않습니다.")
        if item_name not in EQUIPMENT_EFFECTS:
            return await ctx.send("해당 아이템은 장착할 수 없습니다.")
        if len(equipped_gear) >= 2:
            return await ctx.send("장비 슬롯이 가득 찼습니다. (`!장착해제`로 비워주세요)")
        if item_name in equipped_gear:
            return await ctx.send("이미 같은 아이템을 장착하고 있습니다.")

        # 가방에서 제거하고 장비에 추가
        pve_item_bag[item_name] -= 1
        if pve_item_bag[item_name] == 0:
            del pve_item_bag[item_name]
        
        equipped_gear.append(item_name)
        player_data["equipped_gear"] = equipped_gear
        save_data(all_data)
        await ctx.send(f"✅ **{item_name}**을(를) 장착했습니다.")

    @commands.command(name="장착해제")
    async def unequip_item(self, ctx, *, item_name: str):
        """장착한 장비를 해제하여 가방으로 옮깁니다."""
        all_data = load_data()
        player_data = all_data.get(str(ctx.author.id), {})
        equipped_gear = player_data.get("equipped_gear", [])

        if item_name not in equipped_gear:
            return await ctx.send(f"'{item_name}' 아이템을 장착하고 있지 않습니다.")

        # 장비에서 제거하고 가방에 추가
        equipped_gear.remove(item_name)
        pve_item_bag = player_data.get("pve_item_bag", {})
        pve_item_bag[item_name] = pve_item_bag.get(item_name, 0) + 1
        
        player_data["equipped_gear"] = equipped_gear
        save_data(all_data)
        await ctx.send(f"☑️ **{item_name}**을(를) 장착 해제했습니다.")


        
async def setup(bot):
    await bot.add_cog(MonsterCog(bot))
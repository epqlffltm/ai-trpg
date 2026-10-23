# trpg-server/app/rounds/blows.py

"""
타격 하나에 장비가 드는 것(#276). 누가 무슨 무기로 쳤고, 어느 부위에 맞았고, 그 부위의 방어가 얼마인지.

앉은 사람의 타격(app/rounds/checks.py), 몬스터와 NPC 의 공격(app/rounds/monster_attacks.py,
app/rounds/npc_attacks.py)이 같은 규칙을 쓴다.
  - 무기: 앉은 사람은 선언에 적은 물건, 몬스터와 NPC 는 공격에 적은 물건이다. 판정할 때도 착용하고 있어야 한다.
    그사이에 건넸거나 빼앗겼으면 보정이 없다. 공격 보정(attack)이 판정의 보정에 더해진다.
  - 부위: 노렸으면 그 칸, 아니면 서버가 굴린다(app/engine/armor.py). 판정보다 먼저 굴린다. ac 면 목표값이 부위에 달렸다.
    맞는 쪽이 어느 부위에도 방어가 없으면 굴리지 않는다. 어디에 맞아도 같다(모든 부위의 방어만 있어도 같다).
  - 방어: 맞는 쪽이 지금 착용한 것과 타고난 것이다. 앉은 사람은 착용(table_worn), NPC 와 몬스터는 장비 줄의 착용(wear)
    중 아직 지닌 것이다. 몬스터는 부위마다 타고난 방어를 더한다.
  - 커버: 이번 라운드에 엄폐한 앉은 사람은 그 장소의 커버가 있다(app/rounds/covers.py). 세이브 방식에서만 든다.
    관통 굴림은 그 부위의 방어와 커버 중 단단한 것을 넘어야 한다. 관통하면 아머도 커버도 막지 못한다.
결과의 문서(blow)는 판정의 outcome 에 붙는다. 무기도 부위도 방어도 없는 타격이면 붙이지 않는다(그 전과 같다).
DB 를 모른다. 이미 읽어 온 시트와 장면의 마리와 인물을 받는다.
"""

import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from app.assets.scenarios.snapshot import AttackSnapshot, MonsterSnapshot
from app.engine import armor
from app.engine.armor import Pierce, Protection, Save, Worn
from app.engine.ruleset import Ruleset
from app.rounds.cast import CastMember
from app.rounds.effects import Judging
from app.rounds.monster_scene import SceneMonster
from app.tables import monster_items, npc_items
from app.tables.carried import Carried
from app.tables.items import CatalogItem
from app.tables.models import TableMember


@dataclass(frozen=True)
class Weapon:
    """타격에 쓴 무기. 물건과 그 이름과 판정에 더한 공격 보정이다."""

    entry_id: uuid.UUID
    name: str
    bonus: int
    # 관통력. 없으면 0 이다
    ap: int = 0


@dataclass(frozen=True)
class Blow:
    """
    타격 하나에 장비가 든 것. 무기, 맞은 부위, 노렸는가, 그 부위의 방어, 관통 굴림, 맞는 쪽의 불굴 세이브의 값과
    엄폐한 장소의 커버다.

    raise_by 는 맞히는 목표값을 올리는 양(ac), cut 은 피해에서 깎는 양(reduce)이다. 규칙의 방어 방식이 정한다.
    관통했으면 둘 다 0 이다. 세이브(save)는 맞힌 뒤에 따로 굴린다(roll_blow_save).
    """

    weapon: Weapon | None
    location: str | None
    aimed: bool
    defense: int
    raise_by: int
    cut: int
    pierce: Pierce | None = None
    ward: int = 0
    cover: int = 0

    @property
    def bonus(self) -> int:
        """판정의 보정에 더하는 무기의 공격 보정. 무기가 없으면 0 이다."""
        return self.weapon.bonus if self.weapon is not None else 0


# 장비가 들지 않은 타격. 무기도 방어도 없다
NO_BLOW = Blow(weapon=None, location=None, aimed=False, defense=0, raise_by=0, cut=0)


def worn_item(item: CatalogItem | None, slots: Sequence[str]) -> Worn:
    """착용 하나를 방어로 셀 모양으로. 판에 없는 물건이면 방어가 없다."""
    if item is None:
        return Worn(slots=tuple(slots))
    return Worn(slots=tuple(slots), defense=item.defense or 0, guard=item.guard or 0, ward=item.ward or 0)


def member_protection(judging: Judging, member: TableMember) -> Protection:
    """앉은 사람의 지금 방어. 시트의 착용과, 이번 라운드에 엄폐했으면 그 장소의 커버다. 시트가 없으면 방어가 없다."""
    if member.sheet is None:
        return armor.NO_PROTECTION
    worn = armor.protection_of([worn_item(judging.items.get(row.entry_id), row.slots) for row in member.sheet.worn])
    return armor.with_cover(worn, judging.covers.get(member.user_id, 0))


def carried_protection(
    judging: Judging, held: Sequence[Carried], natural: dict[str, int], natural_ward: int = 0
) -> Protection:
    """NPC 나 몬스터의 지금 방어. 아직 지닌 장비 줄 중 착용한 것과, 타고난 방어와 불굴 세이브다."""
    worn = [worn_item(judging.items.get(line.entry_id), line.wear) for line in held if line.equipped and line.wear]
    return armor.protection_of(worn, natural, natural_ward)


def natural_of(definition: MonsterSnapshot) -> dict[str, int]:
    """몬스터의 부위마다 타고난 방어."""
    return {one.slot: one.defense for one in definition.natural_armor}


def monster_protection(judging: Judging, monster: SceneMonster) -> Protection:
    """몬스터 한 마리의 지금 방어."""
    held = monster_items.carried(monster.state, monster.definition)
    return carried_protection(judging, held, natural_of(monster.definition), monster.definition.ward or 0)


def npc_protection(judging: Judging, person: CastMember) -> Protection:
    """NPC 하나의 지금 방어. NPC 는 타고난 방어가 없다."""
    return carried_protection(judging, npc_items.carried(person.npc, person.definition), {})


def weapon_of(item: CatalogItem | None) -> Weapon | None:
    """물건을 무기로. 공격 보정이 없는 물건이면 None."""
    if item is None or item.attack is None:
        return None
    return Weapon(entry_id=item.entry_id, name=item.name, bonus=item.attack, ap=item.ap or 0)


def member_weapon(judging: Judging, member: TableMember, entry_id: uuid.UUID | None) -> Weapon | None:
    """앉은 사람이 선언에 적은 무기. 지금도 착용하고 있어야 한다. 적지 않았거나 벗었으면 None."""
    if entry_id is None or member.sheet is None:
        return None
    if all(row.entry_id != entry_id for row in member.sheet.worn):
        return None
    return weapon_of(judging.items.get(entry_id))


def carried_weapon(judging: Judging, held: Sequence[Carried], attack: AttackSnapshot) -> Weapon | None:
    """NPC 나 몬스터의 공격에 적은 무기. 그 장비 줄을 아직 지니고 착용해야 한다. 아니면 None."""
    if attack.weapon is None:
        return None
    if not any(line.entry_id == attack.weapon and line.equipped and line.wear for line in held):
        return None
    return weapon_of(judging.items.get(attack.weapon))


def monster_weapon(judging: Judging, monster: SceneMonster, attack: AttackSnapshot) -> Weapon | None:
    """몬스터의 공격에 쓰는 무기."""
    return carried_weapon(judging, monster_items.carried(monster.state, monster.definition), attack)


def npc_weapon(judging: Judging, person: CastMember, attack: AttackSnapshot) -> Weapon | None:
    """NPC 의 공격에 쓰는 무기."""
    return carried_weapon(judging, npc_items.carried(person.npc, person.definition), attack)


def plan_blow(judging: Judging, weapon: Weapon | None, protection: Protection, strike: str | None) -> Blow:
    """
    타격 하나를 준비한다. 판정보다 먼저 굴린다. 노렸으면 그 부위, 아니면 부위를 굴리고, 그 부위의 방어를 센다.
    무기에 관통력이 있고 그 부위에 방어나 커버가 있으면 관통을 굴린다. 관통했으면 방어구도 커버도 막지 않는다.

    맞는 쪽이 어느 부위에도 방어가 없으면 부위를 굴리지 않는다(armor.varies_by_slot). 주사위를 쓸 까닭이 없다.
    """
    ruleset = judging.ruleset
    location = strike
    if location is None and armor.varies_by_slot(protection):
        location = armor.roll_location(ruleset, judging.dice)
    defense = armor.defense_at(protection, location) if ruleset.armor is not None else 0
    cover = protection.cover if ruleset.armor is not None else 0
    barrier = armor.barrier(defense, cover)
    pierce = armor.roll_pierce(ruleset, judging.dice, weapon.ap if weapon is not None else 0, barrier)
    holding = armor.holding(defense, pierce)
    return Blow(
        weapon=weapon,
        location=location,
        aimed=strike is not None,
        defense=defense,
        raise_by=armor.target_raise(ruleset, holding),
        cut=armor.damage_cut(ruleset, holding),
        pierce=pierce,
        ward=protection.ward if ruleset.armor is not None else 0,
        cover=cover,
    )


def roll_blow_save(judging: Judging, blow: Blow) -> Save | None:
    """
    맞힌 타격에 맞는 쪽이 세이브를 굴린다. 세이브 방식의 규칙이고 막을 값이 있을 때만이다. 아니면 None.

    관통했으면 아머와 커버 세이브는 없고 불굴 세이브만 남는다(armor.holding).
    """
    defense = armor.holding(blow.defense, blow.pierce)
    cover = armor.holding(blow.cover, blow.pierce)
    return armor.roll_save(judging.ruleset, judging.dice, defense, blow.ward, cover)


def is_saved(save: Save | None) -> bool:
    """세이브로 막았는가. 굴리지 않았으면 막지 않은 것이다."""
    return save is not None and save.saved


def slot_name(ruleset: Ruleset, key: str | None) -> str | None:
    """칸의 이름. 규칙에 없으면 이름표 그대로다."""
    if key is None:
        return None
    return next((slot.name for slot in ruleset.equipment_slots if slot.key == key), key)


def weapon_document(weapon: Weapon | None) -> dict | None:
    """무기를 문서로."""
    if weapon is None:
        return None
    return {'entry_id': str(weapon.entry_id), 'name': weapon.name, 'bonus': weapon.bonus, 'ap': weapon.ap}


def pierce_document(pierce: Pierce | None) -> dict | None:
    """관통 굴림을 문서로. 굴리지 않았으면 None."""
    return None if pierce is None else asdict(pierce)


def save_document(save: Save | None) -> dict | None:
    """세이브 굴림을 문서로. 굴리지 않았으면 None."""
    return None if save is None else asdict(save)


def blow_document(ruleset: Ruleset, blow: Blow, save: Save | None = None) -> dict | None:
    """
    타격에 장비가 든 것을 판정의 outcome 에 붙일 문서로. 무기도 부위도 방어도 세이브도 없으면 None 이다.

    mode 는 규칙의 방어 방식, defense 는 맞은 부위의 방어다. 깎인 피해는 변화(effect)의 rolls 와 amount 의 차이다.
    pierce 는 관통 굴림, save 는 세이브 굴림이다. 굴리지 않았으면 None 이다.
    """
    if blow.weapon is None and blow.location is None and blow.defense == 0 and blow.pierce is None and save is None:
        return None
    return {
        'weapon': weapon_document(blow.weapon),
        'location': blow.location,
        'location_name': slot_name(ruleset, blow.location),
        'aimed': blow.aimed,
        'defense': blow.defense,
        'mode': ruleset.armor.mode.value if ruleset.armor is not None else None,
        'pierce': pierce_document(blow.pierce),
        'save': save_document(save),
    }

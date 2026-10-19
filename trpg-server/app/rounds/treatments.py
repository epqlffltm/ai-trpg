# trpg-server/app/rounds/treatments.py

"""
치료하는 행동의 결과를 정한다(#114 다).

능력과 난이도는 규칙이 정한다(app/engine/treatment.py).
  - 성공하면 나을 시각이 앞당겨지고, 이 장면이 끝나는 때에 닿으면 그 자리에서 낫는다. 나을 때 후유증 표를 굴린다.
  - 실패하면 치료 실패 표를 굴린다. 덧남(나을 시각이 늦춰짐), 피해, 즉사가 나올 수 있다.
  - 시각은 게임 안의 분이다. 닫히는 라운드의 때(Judging.moment)로 정한다.
  - 치료받는 쪽이 떠났거나 죽었거나, 그 부상이 이미 없으면 아무 일도 없다.
DB 를 모른다. 부상과 시트와 NPC 의 상태를 고친다. 저장하지는 않는다.
"""

from dataclasses import asdict, dataclass

from app.engine import health, treatment
from app.engine import injury as injury_rules
from app.engine.action import TreatAction
from app.engine.health import ChangeKind
from app.engine.ruleset import Injury, Mishap, Ruleset
from app.rounds import injuries as round_injuries
from app.rounds.cast import CastMember, find_cast_member
from app.rounds.effects import Judging, mark_hurt, member_effect, npc_effect
from app.tables import injuries, npcs, sheets
from app.tables import state as table_state
from app.tables.injuries import Moment
from app.tables.models import TableMember


@dataclass(frozen=True)
class Patient:
    """
    치료받는 쪽. 앉은 사람의 캐릭터(member)나 이번 장면의 NPC(npc) 중 하나다.

    holder 는 이벤트와 결과에 적을 칸들이다. 캐릭터면 user_id 와 캐릭터 이름, NPC 면 항목의 id 와 장면의 호칭.
    alive 는 지금 치료할 수 있는가다. 떠났거나 죽었으면 아니다.
    """

    holder: dict
    rows: list
    member: TableMember | None = None
    npc: CastMember | None = None
    alive: bool = True


def find_patient(judging: Judging, action: TreatAction) -> Patient:
    """
    치료받는 쪽을 찾는다. 선언을 받은 뒤에 떠났거나 죽었으면 치료할 수 없는 쪽(alive False)으로 돌려준다.

    떠난 사람은 캐릭터 이름을 알 수 없다. 이름이 빈 채로 적힌다.
    """
    if action.npc is not None:
        found = find_cast_member(judging.cast, action.npc)
        if found is None:
            return Patient(holder={'entry_id': str(action.npc), 'name': ''}, rows=[], alive=False)
        holder = {'entry_id': str(found.entry_id), 'name': found.name}
        return Patient(holder=holder, rows=found.npc.injuries, npc=found, alive=not npcs.is_dead(found.npc))
    member = table_state.find_member(judging.table, action.target)
    if member is None or member.sheet is None:
        return Patient(holder={'user_id': str(action.target), 'character_name': ''}, rows=[], alive=False)
    holder = {'user_id': str(member.user_id), 'character_name': member.character_name}
    return Patient(holder=holder, rows=member.sheet.injuries, member=member, alive=not sheets.is_dead(member))


def heals_at_of(row, injury: Injury, moment: Moment) -> int:
    """
    입고 있는 오래 가는 부상이 나을 시각(분). 적혀 있으면 그것이다.

    비어 있으면 시간으로 낫기 전에 입은 것이다(마이그레이션이 채우지만 한 번 더 막는다).
    지금부터 규칙의 기간만큼 뒤로 본다.
    """
    if row.heals_at is not None:
        return row.heals_at
    return injury_rules.heals_at(injury, moment.now)


def left_after(heals_at: int, moment: Moment) -> int:
    """이 장면이 끝난 뒤(다음 라운드가 열린 뒤) 낫기까지 남은 분."""
    return heals_at - moment.scene_end


def treatment_document(ruleset: Ruleset, injury: Injury, patient: Patient) -> dict:
    """
    치료의 결과를 적을 문서의 처음 모양. 무엇을 누구에게 어느 능력과 난이도로 치료했는지다.

    아직 아무 일도 일어나지 않은 것으로 채워 둔다. 일어난 일은 cure 와 mishap 이 덮어쓴다.
    """
    return {
        'injury': injury.key,
        'name': injury.name,
        'ability': ruleset.treatment.ability,
        'difficulty': injury.treat_difficulty,
        'patient': patient.holder,
        'treated': True,
        'heals_at_before': None,
        'heals_at': None,
        'minutes_left': None,
        'healed': False,
        'aftermath': None,
        'mishap': None,
        'died': False,
    }


def cure(judging: Judging, patient: Patient, row, injury: Injury) -> dict:
    """
    치료에 성공했다. 나을 시각을 앞당긴다. 이 장면이 끝나는 때에 닿으면 그 자리에서 낫고 후유증 표를 굴린다.

    문서에 덮어쓸 칸들을 돌려준다.
    """
    moment = judging.moment
    before = heals_at_of(row, injury, moment)
    after = treatment.shortened(before, injury)
    before_document = round_injuries.heals_at_document(before)
    if treatment.is_healed(after, moment.scene_end):
        aftermath = round_injuries.heal(judging.ruleset, judging.dice, row, patient.rows, judging.table.id, moment)
        return {'heals_at_before': before_document, 'healed': True, 'aftermath': aftermath}
    injuries.reschedule(row, after)
    return {
        'heals_at_before': before_document,
        'heals_at': round_injuries.heals_at_document(after),
        'minutes_left': left_after(after, moment),
    }


# 치료 실패가 HP 를 바꾸지 않았을 때의 outcome 칸들
NO_EFFECTS = {'effect': None, 'npc_effect': None}


def mishap_hurt(judging: Judging, patient: Patient, magnitude_key: str) -> dict:
    """
    치료 실패로 치료받는 쪽이 피해를 입는다. 바뀐 것을 outcome 의 칸들(effect, npc_effect)로 돌려준다.

    부상 표는 굴리지 않는다. 새로 맞은 것이 아니라 상처가 덧난 것이다.
    NPC 는 죽이려는 피해가 아니다. HP 가 0 이 되면 쓰러진다.
    """
    magnitude = health.find_magnitude(judging.ruleset, magnitude_key)
    if patient.npc is not None:
        npc = patient.npc.npc
        status_before = npc.status
        change = npcs.change_npc(npc, ChangeKind.DAMAGE, magnitude, False, judging.dice)
        return {
            'effect': None,
            'npc_effect': npc_effect(patient.npc, magnitude_key, change, False, status_before, None),
        }
    sheet = patient.member.sheet
    change = health.change_hp(ChangeKind.DAMAGE, magnitude, sheet.hp, sheet.max_hp, judging.dice)
    sheet.hp = change.after
    mark_hurt(judging, patient.member)
    return {'effect': member_effect(patient.member, magnitude_key, change, None), 'npc_effect': None}


def kill_patient(patient: Patient) -> None:
    """치료 실패의 즉사. 캐릭터면 그 자리에서 죽고, NPC 면 죽음이 된다."""
    if patient.npc is not None:
        npcs.kill(patient.npc.npc)
    else:
        sheets.kill(patient.member.sheet)


def mishap(judging: Judging, patient: Patient, row, injury: Injury) -> tuple[dict, dict]:
    """
    치료에 실패했다. 치료 실패 표를 굴리고, 나온 일을 한다.

    (치료 문서에 덮어쓸 칸들, outcome 의 effect 와 npc_effect) 를 돌려준다.
    덧나면 나을 시각이 늦춰진다. 피해의 등급이 있으면 피해를 입는다. 즉사면 그 자리에서 죽는다.
    """
    moment = judging.moment
    rolled = treatment.roll_mishap(judging.ruleset, judging.dice)
    before = heals_at_of(row, injury, moment)
    fields = {
        'mishap': {
            'roll': rolled.roll,
            'kind': rolled.kind.value,
            'delay_minutes': rolled.delay_minutes,
            'magnitude': rolled.magnitude,
        },
        'heals_at_before': round_injuries.heals_at_document(before),
        'heals_at': round_injuries.heals_at_document(before),
        'minutes_left': left_after(before, moment),
    }
    if rolled.kind == Mishap.FATAL:
        kill_patient(patient)
        return {**fields, 'heals_at': None, 'minutes_left': None, 'died': True}, NO_EFFECTS
    after = treatment.lengthened(before, rolled)
    if after != before:
        injuries.reschedule(row, after)
        fields = {
            **fields,
            'heals_at': round_injuries.heals_at_document(after),
            'minutes_left': left_after(after, moment),
        }
    effects = mishap_hurt(judging, patient, rolled.magnitude) if rolled.magnitude else NO_EFFECTS
    return fields, effects


def apply_treatment(judging: Judging, action: TreatAction, injury: Injury, success: bool) -> dict:
    """
    치료 판정의 결과를 치료받는 쪽에 적용한다. outcome 의 칸들(effect, npc_effect, treatment)로 돌려준다.

    치료받는 쪽이 떠났거나 죽었거나, 그 부상을 이미 입고 있지 않으면(앞사람이 먼저 고쳤다) 아무 일도 없다.
    실패해도 치료 실패 표를 굴리지 않는다. 치료한 것이 없다.
    """
    patient = find_patient(judging, action)
    document = treatment_document(judging.ruleset, injury, patient)
    row = injuries.find_active(patient.rows, injury.key) if patient.alive else None
    if row is None:
        return {**NO_EFFECTS, 'treatment': {**document, 'treated': False}}
    if success:
        return {**NO_EFFECTS, 'treatment': {**document, **cure(judging, patient, row, injury)}}
    fields, effects = mishap(judging, patient, row, injury)
    return {**effects, 'treatment': {**document, **fields}}


def judge_treatment(judging: Judging, member: TableMember, action: TreatAction) -> dict:
    """
    한 사람의 치료하는 행동을 판정하고 그 결과를 정한다. 선언의 outcome 에 적을 문서를 돌려준다.

    능력은 규칙의 치료 능력, 난이도는 그 부상의 치료 난이도다. 치료하는 캐릭터의 부상이 그 능력에 주는 것을 적용한다.
    선언을 받을 때 치료할 수 있는 부상인지 봤다. 규칙은 판에 굳어 있어 그 뒤로 바뀌지 않는다.
    """
    ruleset = judging.ruleset
    injury = treatment.treatable(ruleset, action.injury)
    sheet = member.sheet
    hindrance = round_injuries.hindrance_for(ruleset, sheet.injuries, ruleset.treatment.ability)
    hindered = treatment.treat(ruleset, injury, sheet.abilities, judging.dice, hindrance)
    return {
        **asdict(hindered.check),
        'hindrance': round_injuries.hindrance_document(hindered),
        'called_shot': None,
        **apply_treatment(judging, action, injury, hindered.check.success),
    }

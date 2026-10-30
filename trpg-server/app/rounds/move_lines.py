# trpg-server/app/rounds/move_lines.py

"""
각자 한 일을 한 줄로 적는 법. 순수 함수다.

  예: 기사: 문을 부순다. (근력 판정 성공: 18 + 2 = 20, 목표 20) [있는 곳: 광장]

이 줄은 두 곳에 쓰인다.
  - 가짜 서술자(app/rounds/fake_narrator.py)는 이 줄들을 장면으로 그대로 내보낸다. 장면은 테이블의 모두가 읽는다.
  - 언어 모델의 프롬프트(app/rounds/prompt.py)는 이 줄들을 "[N 라운드에 한 일과 결과]"로 넣는다.
그래서 이 줄에는 모두가 알아도 되는 것만 싣는다. 숨긴 길, 출구, GM 메모처럼 GM 만 아는 것은 프롬프트의 다른 절에 넣는다.

엔진이 정한 결과(판정, 치료, 지목, 물건, 가기와 찾기, 죽음의 굴림, 부상, 몬스터의 공격)를 말로 옮길 뿐이다.
아무것도 정하지 않는다. 몬스터의 줄에는 굴림의 숫자와 도감의 글을 싣지 않는다.
맞붙은 몬스터가 있던 라운드는 차례 순서로 줄을 놓는다(round_lines).
결과의 모양은 app/rounds/narrator.py 에 있다.
"""

from app.engine.ruleset import Outcome
from app.rounds.narrator import (
    AidNote,
    BlowNote,
    CoverNote,
    DeathSaveNote,
    DisarmNote,
    DoorNote,
    DownedStrikeNote,
    DropNote,
    HandOverNote,
    HealNote,
    Impact,
    InjuryNote,
    ItemActionNote,
    ItemNote,
    LootNote,
    MonsterTurnNote,
    Move,
    NamingNote,
    NpcImpact,
    PayNote,
    PutDownNote,
    RecoveryNote,
    ResourceNote,
    RestNote,
    RevivalNote,
    SearchNote,
    SkillNote,
    StealNote,
    TakeNote,
    TargetGoneNote,
    ThrowNote,
    TradeNote,
    TrapNote,
    TrapSetNote,
    TravelNote,
    TreatmentNote,
    TurnNote,
    Verdict,
    WaitNote,
    WakeNote,
    WanderNote,
    WornNote,
)
from app.rounds.time_words import duration_text

# 판정 결과 단계의 이름. 판정 줄과 서술 지침(app/rounds/prompt.py 의 [규칙의 서술 지침])이 같은 이름을 쓴다
OUTCOME_WORDS = {Outcome.SUCCESS: '성공', Outcome.FAILURE: '실패'}


def outcome_of(success: bool) -> Outcome:
    """판정이 성공했는가를 결과 단계로 바꾼다."""
    return Outcome.SUCCESS if success else Outcome.FAILURE


def describe_verdict(verdict: Verdict) -> str:
    """
    판정의 결과를 한 줄로 적는다. 예: (근력 판정 성공: 13 + 2 = 15, 목표 15)

    부상이 영향을 줬으면 그 이름을 붙인다. 예: (근력 판정 실패: 5 - 1 = 4, 목표 15. 전부터 입은 부상의 영향: 팔 골절)
    노려 쳤으면 노린 것을 붙인다. 예: (민첩 판정 성공: 18 + 2 = 20, 목표 20. 노려 치기: 한쪽 눈 잃음)
    """
    result = OUTCOME_WORDS[outcome_of(verdict.success)]
    # 보정이 음수면 "13 - 1" 로 적는다
    sign = '-' if verdict.modifier < 0 else '+'
    sum_ = f'{verdict.roll} {sign} {abs(verdict.modifier)} = {verdict.total}'
    hindered = f'. 전부터 입은 부상의 영향: {", ".join(verdict.hindrances)}' if verdict.hindrances else ''
    aimed = f'. 노려 치기: {verdict.aimed}' if verdict.aimed else ''
    blow = f'. {describe_blow(verdict.blow)}' if verdict.blow is not None else ''
    return f'({verdict.ability} 판정 {result}: {sum_}, 목표 {verdict.target}{hindered}{aimed}{blow})'


# 방어가 한 일(#276). 규칙의 방어 방식마다다
ARMOR_EFFECTS = {'ac': '목표값에 더함', 'reduce': '피해에서 뺌', 'save': '세이브'}
# 세이브의 종류(#276)
SAVE_KINDS = {'armor': '아머', 'cover': '커버', 'ward': '불굴'}


def describe_blow(note: BlowNote) -> str:
    """
    타격에 장비가 든 것을 적는다(#276). 무기, 맞은 부위, 그 부위의 방어가 한 일이다. 없는 것은 뺀다.

    예: 무기: 장검 +2 · 맞은 곳: 몸 · 방어 3(목표값에 더함)
        맞은 곳: 머리(노림) · 방어 0(피해에서 뺌)
        무기: 볼트건 +1 · 맞은 곳: 몸 · 방어 5(세이브) · 관통함 · 불굴 세이브 3: 막음
    """
    parts = []
    if note.weapon is not None:
        parts.append(f'무기: {note.weapon} +{note.weapon_bonus}')
    if note.location is not None:
        parts.append(f'맞은 곳: {note.location}' + ('(노림)' if note.aimed else ''))
    if note.mode is not None:
        parts.append(f'방어 {note.defense}({ARMOR_EFFECTS.get(note.mode, note.mode)})')
    if note.pierced is not None:
        parts.append('관통함' if note.pierced else '관통 못 함')
    if note.saved is not None:
        kind = SAVE_KINDS.get(note.save_kind, note.save_kind)
        parts.append(f'{kind} 세이브 {note.save_value}: ' + ('막음' if note.saved else '못 막음'))
    return ' · '.join(parts)


MISHAPS = {'nothing': '별일 없음', 'pain': '덧나서 아픔', 'worsen': '상처가 덧남', 'fatal': '즉사'}


def describe_treatment(note: TreatmentNote) -> str:
    """
    치료의 결과를 한 줄로 적는다.

    예: → 토르빈의 팔 골절 치료: 앞당겨짐, 낫기까지 2시간 30분
        → 토르빈의 팔 골절 치료: 다 나음. 후유증: 굽은 팔
        → 토르빈의 팔 골절 치료 실패: 상처가 덧남, 50분 늦어짐, 낫기까지 4시간 10분
        → 토르빈의 팔 골절 치료(쓴 물건: 의료 키트 +2): 앞당겨짐, 낫기까지 2시간 30분
    남은 시간은 이 장면이 끝난 뒤부터다(게임 안의 시간, app/rounds/time_words.py).
    붙여 쓴 물건(#277)의 보정은 판정의 보정에 이미 들었다. 무엇을 썼는지만 붙인다(aid_text).
    """
    # 치료받던 사람이 떠났으면 이름을 모른다. 부상만 적는다
    head = f'→ {note.patient}의 {note.injury} 치료' if note.patient else f'→ {note.injury} 치료'
    if note.aid:
        head = f'{head}{aid_text(note.aid)}'
    if not note.treated:
        return f'{head}: 치료할 부상이 이미 없었다'
    if note.mishap is None:
        if note.healed:
            return f'{head}: 다 나음' + (f'. 후유증: {note.aftermath}' if note.aftermath else '')
        return f'{head}: 앞당겨짐' + (f', 낫기까지 {duration_text(note.minutes_left)}' if note.minutes_left else '')
    if note.died:
        return f'{head} 실패: {MISHAPS[note.mishap]}, {note.patient} 죽음'
    parts = [MISHAPS[note.mishap]]
    if note.worsened_minutes:
        parts.append(f'{duration_text(note.worsened_minutes)} 늦어짐')
    # 이 장면 안에 나을 것이면(남은 시간이 없다) 적지 않는다. 라운드가 닫힐 때 시간이 지나 낫는다
    if note.minutes_left is not None and note.minutes_left > 0:
        parts.append(f'낫기까지 {duration_text(note.minutes_left)}')
    return f'{head} 실패: {", ".join(parts)}'


# 이름만 맞힌 지목에 붙는 말. 플레이어가 함께 한 주장("범인은")까지 맞은 것이 아니다
UNSETTLED_CLAIMS = '이름 밖의 주장이 맞는지는 정해지지 않았다'


def describe_naming(note: NamingNote) -> str:
    """
    지목의 결과를 한 줄로 적는다.

    예: → 지목 맞음: 악역영애의 진짜 이름은 비올레타
        → 지목 맞음: 비올레타(이)라는 인물이 이 이야기에 있다. 이름 밖의 주장이 맞는지는 정해지지 않았다
        → 지목 틀림: 악역영애의 진짜 이름은 '로즈'(이)가 아니다
        → 지목 틀림: '로즈'(은)는 맞는 이름이 아니다
    """
    if note.correct:
        if note.label is None:
            return f'→ 지목 맞음: {note.name}(이)라는 인물이 이 이야기에 있다. {UNSETTLED_CLAIMS}'
        if note.label == note.name:
            return f'→ 지목 맞음: {note.name}'
        return f'→ 지목 맞음: {note.label}의 진짜 이름은 {note.name}'
    if note.label is not None:
        return f"→ 지목 틀림: {note.label}의 진짜 이름은 '{note.guess}'(이)가 아니다"
    return f"→ 지목 틀림: '{note.guess}'(은)는 맞는 이름이 아니다"


def describe_healed(healed: list[HealNote]) -> str:
    """시간이 지나 나은 부상들. 예: [나은 부상: 팔 골절(후유증: 굽은 팔), 다리 부상]"""
    names = [note.name + (f'(후유증: {note.aftermath})' if note.aftermath else '') for note in healed]
    return f'[나은 부상: {", ".join(names)}]'


def describe_impact(impact: Impact) -> str:
    """
    HP 가 바뀐 것을 한 줄로 적는다. 동료의 장난(#803)이면 그것과, 장난이라 입지 않은 부상을 붙인다.
    저항으로 막아 낸 부상(#886 ②)도 붙인다.

    피해의 성질(#886 ③)이 있으면 피해 앞에 그 이름을, 받은 단계(저항, 면역, 약점)를 괄호에 붙인다.

    예: → 엘프 피해 3 (HP 7/10)
        → 영애 피해 6 (HP 1/10, 장난). 장난이라 입지 않은 부상: 팔 골절
        → 드워프 피해 9 (HP 1/12). 막아 낸 부상: 중독
        → 엘프 화염 피해 2 (HP 8/10, 저항)
    """
    word = change_word(impact.kind, impact.nature)
    state = (
        f'HP {impact.hp}/{impact.max_hp}'
        + (', 쓰러짐' if impact.downed else '')
        + (', 장난' if impact.prank else '')
        + level_tag(impact.level)
    )
    line = f'→ {impact.character_name} {word} {impact.amount} ({state})' + new_injury(impact.injury)
    line += resisted_injury(impact.resisted)
    return line + (f'. 장난이라 입지 않은 부상: {impact.spared}' if impact.spared else '')


# 피해의 성질을 받은 단계(#886 ③)를 서술자에게 주는 말
LEVEL_WORDS = {'resist': '저항', 'immune': '면역', 'vulnerable': '약점'}


def change_word(kind: str, nature: str | None) -> str:
    """HP 의 변화의 말. 피해, 회복, 성질이 있는 피해면 그 이름을 앞에 붙인다(화염 피해, #886 ③)."""
    if kind != 'damage':
        return '회복'
    return f'{nature} 피해' if nature else '피해'


def level_tag(level: str | None) -> str:
    """괄호 안에 붙일 받은 단계(#886 ③). 그대로 받았으면 빈 글이다. 예: ", 저항"."""
    return f', {LEVEL_WORDS[level]}' if level in LEVEL_WORDS else ''


def new_injury(name: str | None) -> str:
    """새로 입은 부상을 결과 줄 뒤에 붙일 글. 없으면 빈 글이다. 예: ". 새 부상: 팔 골절"."""
    return f'. 새 부상: {name}' if name else ''


def describe_injuries(injuries: list[InjuryNote]) -> str:
    """입고 있는 부상들을 한 덩어리로 적는다. 예: 팔 골절(한쪽 팔이 부러져 제대로 쓰지 못한다)"""
    return ', '.join(f'{injury.name}({injury.fact})' for injury in injuries)


def describe_npc_impact(impact: NpcImpact) -> str:
    """
    NPC 의 HP 가 바뀐 것을 한 줄로 적는다. 숫자는 양만 적는다. 몬스터도 이 줄이다.

    예: → 악역영애 피해 5 (크게 다침)
        → 수로 쥐 화염 피해 8 (쓰러짐, 약점)
    """
    word = change_word(impact.kind, impact.nature)
    condition = impact.condition + level_tag(impact.level)
    line = f'→ {impact.name} {word} {impact.amount} ({condition})' + new_injury(impact.injury)
    return line + resisted_injury(impact.resisted)


def resisted_injury(name: str | None) -> str:
    """
    면역이나 저항으로 막아 입지 않은 부상을 결과 줄 뒤에 붙일 글(#799, #886 ②). 없으면 빈 글이다.

    예: ". 막아 낸 부상: 중독"
    """
    return f'. 막아 낸 부상: {name}' if name else ''


def describe_wake(wake: WakeNote) -> str:
    """
    깨어난 인물이 쓰러진 동안 빼앗긴 것을 알아챈 것을 한 줄로 적는다.

    예: (깨어난 악역영애 이(가) 품이 빈 것을 알아챘다. 태도: 경계)
    """
    return f'(깨어난 {wake.name} 이(가) 품이 빈 것을 알아챘다. 태도: {wake.attitude})'


def describe_drop(drop: DropNote) -> str:
    """
    몬스터를 쓰러뜨려 얻은 물건을 한 줄로 적는다. 더 들 수 없어 잃은 것이 있으면 그것도 적는다.

    예: (얻은 물건: 늑대 가죽 2개, 송곳니 → 엘프)
        (얻은 물건: 치유 물약 → 엘프. 치유 물약 1개는 더 들 수 없어 잃었다)
        (얻을 물건: 치유 물약 2개 → 엘프. 더 들 수 없어 모두 잃었다)
    """
    got = ', '.join(describe_stack(one.name, one.count) for one in drop.items if one.count)
    lost = ', '.join(describe_stack(one.name, one.lost, always=True) for one in drop.items if one.lost)
    if not got:
        return f'(얻을 물건: {lost} → {drop.receiver}. 더 들 수 없어 모두 잃었다)'
    if not lost:
        return f'(얻은 물건: {got} → {drop.receiver})'
    return f'(얻은 물건: {got} → {drop.receiver}. {lost}는 더 들 수 없어 잃었다)'


def describe_stack(name: str, count: int, always: bool = False) -> str:
    """물건 몇 개를 적는다. 하나면 개수를 적지 않는다(소지품과 같다). always 면 하나라도 적는다."""
    return f'{name} {count}개' if always or count != 1 else name


def describe_idle(move: Move) -> str:
    """
    선언을 내지 않은 캐릭터를 뭐라고 적을지 정한다.

    새로 들어온 캐릭터를 가장 먼저 본다. 이 라운드에 한 일이 없는 것은 들어온 라운드이기 때문이다.
    죽은 캐릭터는 쓰러져 있기도 하다. 죽음을 쓰러짐보다 먼저 본다.
    """
    if move.replaces is not None:
        return f'죽은 {move.replaces}의 뒤를 이어 새로 이야기에 들어온다.'
    if move.dead:
        return '죽었다.'
    return '쓰러져 있다.' if move.downed else '아무것도 하지 않았다.'


FATES = {'dying': '죽어 가는 중', 'stable': '고비를 넘김', 'dead': '죽음'}


def describe_death_save(note: DeathSaveNote) -> str:
    """죽음의 굴림을 한 줄로 적는다. 예: (죽음의 굴림 실패: 7, 목표 10. 성공 1, 실패 2, 죽어 가는 중)"""
    result = '성공' if note.success else '실패'
    counts = f'성공 {note.successes}, 실패 {note.failures}'
    return f'(죽음의 굴림 {result}: {note.roll}, 목표 {note.target}. {counts}, {FATES[note.fate]})'


# 휴식의 길이와, 휴식이 깨진 까닭을 서술자에게 주는 말
REST_LENGTHS = {'short': '짧은 휴식', 'long': '긴 휴식'}
REST_BREAKS = {
    'hurt': '맞아서 쉬지 못했다',
    'downed': '쓰러져 쉬지 못했다',
    'dead': '죽어 쉬지 못했다',
    'ambushed': '몬스터가 덮쳐 쉬지 못했다',
}


def describe_rest(note: RestNote) -> str:
    """
    쉬는 행동의 결과를 한 줄로 적는다.

    예: (쉬기: 긴 휴식, HP 2 → 10/10)
        (쉬기: 짧은 휴식. 맞아서 쉬지 못했다)
    """
    length = REST_LENGTHS.get(note.length, '휴식')
    if not note.rested:
        return f'(쉬기: {length}. {REST_BREAKS.get(note.reason, "쉬지 못했다")})'
    shifts = ''.join(f', {describe_resource(one)}' for one in note.resources)
    return f'(쉬기: {length}, HP {note.before} → {note.after}/{note.max_hp}{shifts})'


def describe_resource(note: ResourceNote) -> str:
    """
    수치 하나(#804). 바뀐 것이면 전과 뒤를, 아니면 지금 값을 적는다. 숨긴 수치는 말로만 적는다.
    저항으로 막아 내 바뀌지 않았으면(#886 ②) 그것만 적는다.

    예: 마나 1 → 6/6
        마나 3/6
        광기 모자람
        마나 막아 냄
    """
    if note.resisted:
        return f'{note.name} 막아 냄'
    if note.word is not None:
        return f'{note.name} {note.word}'
    if note.before is None:
        return f'{note.name} {note.value}/{note.max}'
    return f'{note.name} {note.before} → {note.value}/{note.max}'


# 기다림이 깨진 까닭을 서술자에게 주는 말
WAIT_BREAKS = {'hurt': '싸움이 벌어져 시간이 건너뛰지 않았다', 'not_all': '모두가 기다리지 않아 시간이 건너뛰지 않았다'}


def describe_wait(note: WaitNote) -> str:
    """
    기다리는 행동의 결과를 한 줄로 적는다. 실제로 흐르는 시간은 [시각]에 있다.

    예: (기다리기: 3일)
        (기다리기: 3일. 모두가 기다리지 않아 시간이 건너뛰지 않았다)
    """
    asked = duration_text(note.minutes)
    if not note.waited:
        return f'(기다리기: {asked}. {WAIT_BREAKS.get(note.reason, "시간이 건너뛰지 않았다")})'
    return f'(기다리기: {asked})'


def describe_wander(note: WanderNote) -> str:
    """
    무작위 조우로 나온 무리를 한 줄로 적는다(#283). 엔진이 굴려 놓았다. 쉬는 중이었으면 덮쳐 쉬기가 깨졌다.

    예: (조우: 수로 쥐 3마리가 나타났다)
        (조우: 쉬는 중에 해골 병사 1마리가 덮쳤다)
    """
    if note.cause == 'rest':
        return f'(조우: 쉬는 중에 {note.monster} {note.count}마리가 덮쳤다)'
    return f'(조우: {note.monster} {note.count}마리가 나타났다)'


def describe_cover(note: CoverNote) -> str:
    """
    엄폐하는 행동의 결과를 한 줄로 적는다(#276). 막았는지는 판정과 차례의 줄의 세이브에 있다.

    예: (엄폐: 무너진 담, 커버 4)
        (엄폐: 숨을 곳이 없어 숨지 못했다)
    """
    if note.value <= 0:
        return '(엄폐: 숨을 곳이 없어 숨지 못했다)'
    return f'(엄폐: {note.place}, 커버 {note.value})'


def describe_revival(note: RevivalNote) -> str:
    """
    되살아나기의 결과를 한 줄로 적는다.

    예: (되살아나기: 오래 쉬어 정신이 돌아왔다, HP 1)
        (되살아나기: 아직 깨어나지 못했다. 고비는 넘겼다)
    """
    if note.success:
        return f'(되살아나기: 오래 쉬어 정신이 돌아왔다, HP {note.hp})'
    return '(되살아나기: 아직 깨어나지 못했다. 고비는 넘겼다)'


def describe_recovery(note: RecoveryNote) -> str:
    """시간이 흘러 저절로 회복한 것을 한 줄로 적는다. 예: (시간이 지나 회복: HP 3 → 8/10)"""
    return f'(시간이 지나 회복: HP {note.before} → {note.after}/{note.max_hp})'


# 물건을 쓰거나 건네지 못한 까닭을 서술자에게 주는 말
ITEM_FAILURES = {
    'not_held': '가지고 있지 않았다',
    'target_gone': '받을 사람이 없었다',
    'too_many': '받는 쪽이 더 가질 수 없었다',
    'friendly_fire_off': '동료를 해칠 수 없게 바뀌었다',
}


def describe_throw(note: ThrowNote) -> str:
    """
    물건을 던진 것을 한 줄로 적는다(#277). 판정 앞에 붙는다. 맞았는지는 뒤의 판정과 피해가 적는다.

    예: (던진 물건: 화염병 → 수로 쥐 1)
        (던지려던 물건: 화염병. 가지고 있지 않았다)
        (던지려던 물건: 화염병 → 수로 쥐 1)   겨눈 몬스터가 없었다. 그 까닭은 뒤의 줄이 적는다
        (던진 물건: 독 병 → 수로 쥐 1) [입힌 부상: 중독]   맞혀 물건의 효과가 들었다(#801)
    """
    to = f' → {note.target}' if note.target else ''
    if note.done:
        tags = [*effect_tags(note.cured, note.injured, note.resisted, note.spared), *resource_tags(note.resources)]
        return ' '.join([f'(던진 물건: {note.name}{to})', *tags])
    if note.reason == 'not_held':
        return f'(던지려던 물건: {note.name}{to}. {ITEM_FAILURES["not_held"]})'
    return f'(던지려던 물건: {note.name}{to})'


# 기술을 쓰지 못한 까닭(#805)을 서술자에게 줄 말
SKILL_FAILURES = {
    'not_known': '그 기술을 모른다',
    'cost_short': '비용이 모자랐다',
    'target_gone': '받을 쪽이 없었다',
    'friendly_fire_off': '동료를 해칠 수 없게 바뀌었다',
}


def describe_skill(note: SkillNote) -> str:
    """
    기술을 쓴 결과(#805)를 한 줄로 적는다. 낸 비용, HP 의 변화, 부상과 수치에 한 일을 붙인다.
    물건을 쓴 줄과 같은 모양이다.

    예: (쓴 기술: 치유의 손길 → 영애, 마나 5 → 3/7) → 영애 회복 3 (HP 8/10)
        (쓰려던 기술: 화염 방패. 비용이 모자랐다)
        (쓴 기술: 마력 화살 → 수로 쥐 1, 마나 4 → 3/7)   굴린 기술(#805 ②)은 판정 앞에 붙는다. 맞았는지는 판정이 적는다
    """
    to = f' → {note.target}' if note.target else ''
    if not note.done:
        return f'(쓰려던 기술: {note.name}{to}. {SKILL_FAILURES.get(note.reason, "하지 못했다")})'
    paid = ''.join(f', {describe_resource(one)}' for one in note.cost)
    parts = [f'(쓴 기술: {note.name}{to}{paid})']
    if note.impact:
        parts.append(describe_impact(note.impact))
    parts.extend(effect_tags(note.cured, note.injured, note.resisted, note.spared))
    parts.extend(resource_tags(note.resources))
    return ' '.join(parts)


def describe_item_action(note: ItemActionNote) -> str:
    """
    물건을 쓰거나 건넨 결과를 한 줄로 적는다. HP 가 바뀌었으면 그 변화를, 부상을 풀었으면 풀린 부상을,
    입혔으면 생긴 부상과 면역이나 저항으로 막아 낸 부상을 붙인다(#800, #886 ②).

    예: (쓴 물건: 치유 물약) → 엘프 회복 3 (HP 8/10)
        (쓴 물건: 해독제 → 영애) [풀린 부상: 중독]
        (쓴 물건: 독 바른 단검 → 해골 병사) [막아 낸 부상: 중독]
        (건넨 물건: 밧줄 1개 → 영애)
        (쓰려던 물건: 치유 물약. 가지고 있지 않았다)
    """
    what = note.name if note.kind == 'use' else f'{note.name} {note.count}개'
    to = f' → {note.target}' if note.target else ''
    if not note.done:
        verb = '쓰려던' if note.kind == 'use' else '건네려던'
        return f'({verb} 물건: {what}{to}. {ITEM_FAILURES.get(note.reason, "하지 못했다")})'
    verb = '쓴' if note.kind == 'use' else '건넨'
    parts = [f'({verb} 물건: {what}{to})']
    if note.impact:
        parts.append(describe_impact(note.impact))
    parts.extend(effect_tags(note.cured, note.injured, note.resisted, note.spared))
    parts.extend(resource_tags(note.resources))
    return ' '.join(parts)


def resource_tags(shifts: list[ResourceNote]) -> list[str]:
    """물건의 맞추기(#804)가 바꾼 수치를 줄 뒤에 붙일 조각. 없으면 빈 목록이다. 예: [수치: 마나 2 → 5/6]"""
    if not shifts:
        return []
    return [f'[수치: {", ".join(describe_resource(one) for one in shifts)}]']


def effect_tags(cured: list[str], injured: list[str], resisted: list[str], spared: list[str] = ()) -> list[str]:
    """
    물건의 효과가 부상에 한 일을 줄 뒤에 붙일 조각들(#800, #801, #803). 없으면 빈 목록이다.

    예: [풀린 부상: 중독] [입힌 부상: 기절] [막아 낸 부상: 중독] [장난이라 입지 않은 부상: 팔 골절]
    """
    tags = []
    if cured:
        tags.append(f'[풀린 부상: {", ".join(cured)}]')
    if injured:
        tags.append(f'[입힌 부상: {", ".join(injured)}]')
    if resisted:
        tags.append(f'[막아 낸 부상: {", ".join(resisted)}]')
    if spared:
        tags.append(f'[장난이라 입지 않은 부상: {", ".join(spared)}]')
    return tags


def describe_worn(worn: list[WornNote]) -> str:
    """착용한 물건들을 한 줄로 적는다(#276). 예: 대검(주손·보조손), 사슬 갑옷(몸)"""
    return ', '.join(f'{note.name}({"·".join(note.slots)})' for note in worn)


def describe_items(items: list[ItemNote]) -> str:
    """가진 물건들을 한 줄로 적는다. 하나뿐이면 개수를 적지 않는다. 예: 치유 물약 2개, 밧줄"""
    return ', '.join(item.name if item.count == 1 else f'{item.name} {item.count}개' for item in items)


# 가지 못한 까닭을 서술자에게 주는 말. 넘기에 실패한 것(cross_failed)은 cross_failure 가 따로 말한다
TRAVEL_FAILURES = {
    'not_adjacent': '그쪽으로 이어진 길이 없었다',
    'locked': '문이 잠겨 있었고 맞는 열쇠가 없었다',
    'barred': '반대쪽에 빗장이 걸려 있었다',
}
# 업고 가지 못한 까닭을 서술자에게 주는 말. 업은 사람이 가지 못한 것(not_moved)은 가지 못한 줄이 말한다
CARRY_FAILURES = {
    'standing': '이미 일어나 있어 업지 않았다',
    'dead': '숨을 거두어 쓰러진 곳에 남았다',
    'elsewhere': '그 자리에 없었다',
}


def carry_text(note: TravelNote) -> str:
    """업고 간 것을 간 곳의 줄 끝에 붙일 말. 업으려 하지 않았으면 빈 말이다."""
    if note.carried is None:
        return ''
    if note.carry_reason is None:
        return f', {note.carried}을(를) 업고'
    return f'. {note.carried}은(는) {CARRY_FAILURES.get(note.carry_reason, "업지 못했다")}'


def cross_failure(note: TravelNote) -> str:
    """길을 넘지 못한 까닭의 말(#281). 무슨 판정에 실패했는지와, 다쳤으면 다쳤다는 것."""
    hurt = '. 실패해 다쳤다' if note.hurt else ''
    return f'{note.cross} 판정에 실패해 넘지 못했다{hurt}'


def travel_failure(note: TravelNote) -> str:
    """가지 못한 까닭의 말."""
    if note.reason == 'cross_failed':
        return cross_failure(note)
    return TRAVEL_FAILURES.get(note.reason, '가지 못했다')


def passage_text(note: TravelNote) -> str:
    """길의 조건을 채우고 간 것을 간 곳의 줄에 붙일 말(#281). 열쇠로 연 문, 넘기 판정. 없었으면 빈 말이다."""
    unbarred = ', 빗장을 풀고' if note.unbarred else ''
    unlocked = ', 열쇠로 문을 열고' if note.unlocked else ''
    crossed = f', {note.cross} 판정에 성공해 넘어' if note.cross else ''
    return f'{unbarred}{unlocked}{crossed}'


def describe_travel(note: TravelNote) -> str:
    """
    맵에서 한 칸 간 결과를 한 줄로 적는다.

    예: (간 곳: 성문 → 숲)
        (간 곳: 성문 → 숲, 3시간 걸림)
        (간 곳: 성문 → 숲, 3시간 걸림, 약사을(를) 업고)
        (간 곳: 성문 → 숲. 약사은(는) 숨을 거두어 쓰러진 곳에 남았다)
        (간 곳: 광장 → 탑, 열쇠로 문을 열고, 근력 판정에 성공해 넘어)
        (가려던 곳: 광장. 그쪽으로 이어진 길이 없었다)
        (가려던 곳: 탑. 근력 판정에 실패해 넘지 못했다. 실패해 다쳤다)
        (간 곳: 광장 → 절벽 위, 근력 판정에 성공해 넘어)(쓴 물건: 밧줄 +2)
        (간 곳: 광장 → 숲)(덫: 올가미. 민첩 판정에 실패해 걸렸다)
    넘기에 붙여 쓴 물건(#802)이 있으면 뒤에 붙는다. 들어간 곳에서 터진 덫(#806)은 그 뒤에 하나씩 붙는다.
    """
    tool = aid_text(note.aid) if note.aid else ''
    if not note.moved:
        return f'(가려던 곳: {note.to_place}. {travel_failure(note)}){tool}'
    start = f'{note.from_place} → ' if note.from_place else ''
    took = f', {duration_text(note.travel_minutes)} 걸림' if note.travel_minutes else ''
    sprung = ''.join(trap_text(trap) for trap in note.traps)
    return f'(간 곳: {start}{note.to_place}{took}{passage_text(note)}{carry_text(note)}){tool}{sprung}'


def trap_text(note: TrapNote) -> str:
    """
    들어간 곳에서 터진 덫 하나의 말(#806).

    예: (덫: 올가미. 민첩 판정에 성공해 피했다)
        (덫: 올가미. 민첩 판정에 실패해 걸렸다)
    """
    if note.avoided:
        return f'(덫: {note.name}. {note.check} 판정에 성공해 피했다)'
    return f'(덫: {note.name}. {note.check} 판정에 실패해 걸렸다)'


# 문을 다룬 것의 말. 해낸 것이다(#281). 잠그기와 열기는 장치마다 다르다
DOOR_DONE = {
    ('lock', 'lock'): '열쇠로 문을 잠갔다',
    ('lock', 'bar'): '빗장을 걸었다',
    ('unlock', 'lock'): '열쇠로 문을 열었다',
    ('unlock', 'bar'): '빗장을 풀었다',
    ('pick', None): '자물쇠를 땄다',
    ('force', None): '문을 부숴 열었다',
    ('repair', None): '부서진 문을 고쳤다',
    ('replace', None): '자물쇠를 새것으로 바꿔 달았다',
}
# 문을 다루지 못한 까닭의 말. 따기와 부수기의 실패는 door_failure 가 따로 말한다
DOOR_FAILURES = {
    'no_key': '맞는 열쇠가 없었다',
    'wrong_side': '빗장의 반대쪽이라 손이 닿지 않았다',
    'broken': '부서진 문이라 잠기지 않았다',
    'already': '이미 그렇게 되어 있었다',
    'no_tool': '딸 도구가 없었다',
}
# 행동마다의 까닭의 말. 같은 까닭이라도 행동마다 뜻이 다르다. 없으면 DOOR_FAILURES 의 말이다
ACT_FAILURES = {
    ('pick', 'no_pick'): '따지 못하는 자물쇠였다',
    ('repair', 'already'): '부서진 문이 아니었다',
    ('repair', 'no_tool'): '고칠 도구가 없었다',
    ('replace', 'broken'): '부서진 문이라 먼저 고쳐야 했다',
    ('replace', 'locked'): '자물쇠가 잠겨 있어 떼지 못했다',
    ('replace', 'no_item'): '달 자물쇠가 없었다',
    ('replace', 'used'): '이미 단 적이 있는 자물쇠였다',
}
# 무엇을 하려 했는지의 말(못 했을 때)
DOOR_TRIES = {
    'lock': '잠그려',
    'unlock': '열려',
    'pick': '따려',
    'force': '부수려',
    'repair': '고치려',
    'replace': '새 자물쇠로 바꾸려',
}


def door_failure(note: DoorNote) -> str:
    """문을 다루지 못한 까닭의 말. 판정에 실패했으면 무슨 판정인지 말한다."""
    if note.reason == 'failed':
        return f'{note.check} 판정에 실패했다'
    if (note.act, note.reason) in ACT_FAILURES:
        return ACT_FAILURES[(note.act, note.reason)]
    return DOOR_FAILURES.get(note.reason, '하지 못했다')


def describe_door(note: DoorNote) -> str:
    """
    길의 문을 다룬 결과를 한 줄로 적는다(#281). 지나가지는 않았다. 붙여 쓴 물건(#802)이 있으면 뒤에 붙는다.

    예: (문: 광장 쪽 문. 빗장을 걸었다)
        (문: 탑 쪽 문. 민첩 판정에 성공해 자물쇠를 땄다)
        (문: 탑 쪽 문을 따려 했다. 민첩 판정에 실패했다)(쓴 물건: 락픽 +1, 부러짐)
    """
    tool = aid_text(note.aid) if note.aid else ''
    if not note.done:
        return f'(문: {note.other_end} 쪽 문을 {DOOR_TRIES.get(note.act, "다루려")} 했다. {door_failure(note)}){tool}'
    rolled = f'{note.check} 판정에 성공해 ' if note.check else ''
    return f'(문: {note.other_end} 쪽 문. {rolled}{DOOR_DONE.get((note.act, note.device), "문을 다뤘다")}){tool}'


def aid_text(aid: AidNote) -> str:
    """
    붙여 쓴 물건(#802)의 꼬리. 보정이 0 이면 숫자를 적지 않는다. 실패해서 부러졌으면 그것도 적는다.

    예: (쓴 물건: 의료 키트 +2), (쓴 물건: 공구), (쓴 물건: 락픽 +1, 부러짐)
    """
    bonus = f' +{aid.bonus}' if aid.bonus else ''
    broken = ', 부러짐' if aid.broken else ''
    return f'(쓴 물건: {aid.name}{bonus}{broken})'


def describe_search(note: SearchNote) -> str:
    """
    숨긴 길과 숨긴 물건을 찾은 결과를 한 줄로 적는다. 찾지 못했으면 숨긴 것이 없었는지 있었는지 말하지 않는다.

    찾은 길은 이제 아는 길이라 "숨은 길"이라 부르지 않는다. 맵 절의 "숨은 길은 드러내지 마라"에 눌리지 않게 한다.
    찾은 물건도 "숨은 물건"이라 부르지 않는다. 이미 찾은 사람이 가졌다.

    예: (찾기: 길을 찾아냈다. 지하실(으)로 이어진다)
        (찾기: 은열쇠을(를) 찾아 챙겼다)
        (찾기: 덫을 찾아냈다. 올가미)
        (찾기: 찾은 것이 없다)
    """
    parts = []
    if note.found:
        parts.append(f'길을 찾아냈다. {", ".join(note.found)}(으)로 이어진다')
    if note.items:
        parts.append(f'{describe_items(note.items)}을(를) 찾아 챙겼다')
    if note.traps:
        parts.append(f'덫을 찾아냈다. {", ".join(note.traps)}')
    return f'(찾기: {". ".join(parts) or "찾은 것이 없다"})'


# 다 줍지 못한 까닭의 말(app/rounds/place_item_actions.py 의 Reason)
TAKE_SHORT_WORDS = {
    'gone': '남아 있지 않았다',
    'not_enough': '남은 것만 주웠다',
    'full': '더 들 수 없어 그만큼만 주웠다',
}


def describe_take(note: TakeNote) -> str:
    """
    놓인 물건을 주운 결과를 한 줄로 적는다.

    예: (줍기: 치유 물약 2개를 주웠다)
        (줍기: 치유 물약 1개를 주웠다. 남은 것만 주웠다)
        (줍기: 치유 물약이(가) 남아 있지 않았다)
        (줍기: 치유 물약을(를) 더 들 수 없어 줍지 못했다)
    """
    if not note.taken and note.reason == 'gone':
        return f'(줍기: {note.name}이(가) {TAKE_SHORT_WORDS["gone"]})'
    if not note.taken:
        return f'(줍기: {note.name}을(를) 더 들 수 없어 줍지 못했다)'
    taken = f'{note.name} {note.taken}개를 주웠다'
    if note.reason is None:
        return f'(줍기: {taken})'
    return f'(줍기: {taken}. {TAKE_SHORT_WORDS[note.reason]})'


def describe_trap_set(note: TrapSetNote) -> str:
    """
    덫을 놓은 결과를 한 줄로 적는다(#806).

    예: (덫 놓기: 올가미을(를) 숨겨 놓았다)
        (덫 놓기: 올가미을(를) 가지고 있지 않았다)
    """
    if note.set:
        return f'(덫 놓기: {note.name}을(를) 숨겨 놓았다)'
    return f'(덫 놓기: {note.name}을(를) 가지고 있지 않았다)'


# 해제를 굴리지 못한 까닭의 말(app/rounds/trap_actions.py 의 DisarmReason)
DISARM_FAILURES = {'gone': '덫이 이미 없었다', 'elsewhere': '덫이 있는 곳에 없었다'}


def describe_disarm(note: DisarmNote) -> str:
    """
    덫을 해제한 결과를 한 줄로 적는다(#806 ①-b).

    예: (해제: 올가미. 민첩 판정에 성공해 거둬 챙겼다)
        (해제: 올가미. 민첩 판정에 실패했다. 덫은 그대로다)
        (해제: 올가미. 민첩 판정에 크게 실패해 덫이 터졌다)
        (해제: 덫이 이미 없었다)
    """
    if note.reason is not None:
        return f'(해제: {DISARM_FAILURES.get(note.reason, "해제하지 못했다")})'
    if note.done:
        return f'(해제: {note.name}. {note.check} 판정에 성공해 거둬 챙겼다)'
    if note.sprung:
        return f'(해제: {note.name}. {note.check} 판정에 크게 실패해 덫이 터졌다)'
    return f'(해제: {note.name}. {note.check} 판정에 실패했다. 덫은 그대로다)'


def describe_put_down(note: PutDownNote) -> str:
    """
    내려놓은 결과를 한 줄로 적는다.

    예: (내려놓기: 밧줄 1개를 내려놓았다)
        (내려놓기: 밧줄 2개를 가지고 있지 않았다)
    """
    if note.put:
        return f'(내려놓기: {note.name} {note.count}개를 내려놓았다)'
    return f'(내려놓기: {note.name} {note.count}개를 가지고 있지 않았다)'


def describe_steal(note: StealNote) -> str:
    """
    훔친 결과를 한 줄로 적는다.

    예: (훔치기: 수로 쥐 1 에게서 송곳니 1개를 몰래 빼냈다)
        (훔치기: 수로 쥐 1 에게서 송곳니를 훔치다 들켰다. 수로 쥐 1 이 노린다)
        (훔치기: 악역영애 에게서 부채를 훔치다 들켰다. 악역영애 이(가) 적대한다. 싸움이 붙었다)
        (훔치기: 수로 쥐 1 은 송곳니를 이미 지니지 않았다)
    """
    if note.stolen:
        return f'(훔치기: {note.victim} 에게서 {note.name} {note.count}개를 몰래 빼냈다)'
    if note.caught:
        return f'(훔치기: {note.victim} 에게서 {note.name}을(를) 훔치다 들켰다. {caught_consequence(note)})'
    return f'(훔치기: {note.victim} 은(는) {note.name}을(를) 이미 지니지 않았다)'


def caught_consequence(note: StealNote) -> str:
    """
    들킨 뒤에 일어난 일. 몬스터는 도둑을 노린다. NPC 는 적대하고(이미 적대였으면 그대로), 싸움이 붙었으면 그것도.

    NPC 는 아직 공격하지 않는다. 싸움이 붙었다는 것은 엔진이 싸운 것으로 친다는 사실이다.
    """
    if not note.npc:
        return f'{note.victim} 이(가) 노린다'
    attitude = f'{note.victim} 이(가) 적대한다' if note.hostile else f'{note.victim} 은(는) 이미 적대하고 있다'
    return f'{attitude}. 싸움이 붙었다' if note.fight else attitude


def describe_loot(note: LootNote) -> str:
    """
    빼앗은 결과를 한 줄로 적는다.

    예: (빼앗기: 수로 쥐 1 에게서 송곳니 1개를 가져갔다)
        (빼앗기: 수로 쥐 1 에게서 금화 3개를 가져갔다. 더 들 수 없어 남은 것은 두었다)
        (빼앗기: 수로 쥐 1 은(는) 송곳니를 이미 지니지 않았다)
        (빼앗기: 악역영애 이(가) 깨어 있어 가져가지 못했다)
        (빼앗기: 금화을(를) 더 들 수 없어 가져가지 못했다)
    """
    if note.looted:
        line = f'(빼앗기: {note.victim} 에게서 {note.name} {note.count}개를 가져갔다'
        return line + ('. 더 들 수 없어 남은 것은 두었다)' if note.reason == 'full' else ')')
    if note.reason == 'awake':
        return f'(빼앗기: {note.victim} 이(가) 깨어 있어 가져가지 못했다)'
    if note.reason == 'gone':
        return f'(빼앗기: {note.victim} 은(는) {note.name}을(를) 이미 지니지 않았다)'
    return f'(빼앗기: {note.name}을(를) 더 들 수 없어 가져가지 못했다)'


# 사거나 팔거나 돈을 건네지 못한 까닭을 서술자에게 주는 말(app/rounds/trades.py 의 Reason)
TRADE_FAILURES = {
    'unavailable': '상인이 거래할 수 없었다',
    'out_of_stock': '상인에게 그만큼이 없었다',
    'not_enough_money': '돈이 모자랐다',
    'not_held': '그만큼 가지고 있지 않았다',
    'full': '더 가질 수 없었다',
    'too_much_money': '돈을 더 가질 수 없었다',
    'target_gone': '받을 사람이 없었다',
}


def describe_trade(note: TradeNote) -> str:
    """
    상인과 사고판 결과를 한 줄로 적는다(#278).

    예: (산 물건: 상인 에게서 치유 물약 2개. 금화 20닢을 냈다)
        (판 물건: 상인 에게 늑대 가죽 3개. 금화 15닢을 받았다)
        (사려던 물건: 상인 에게서 치유 물약 2개(금화 20닢). 돈이 모자랐다)
    """
    what = f'{note.name} {note.count}개'
    buying = note.side == 'buy'
    whom = f'{note.merchant} 에게서' if buying else f'{note.merchant} 에게'
    if not note.traded:
        verb = '사려던' if buying else '팔려던'
        return f'({verb} 물건: {whom} {what}({note.price}). {TRADE_FAILURES.get(note.reason, "하지 못했다")})'
    verb, money_verb = ('산', '냈다') if buying else ('판', '받았다')
    return f'({verb} 물건: {whom} {what}. {note.price}을(를) {money_verb})'


def describe_pay(note: PayNote) -> str:
    """
    돈을 건넨 결과를 한 줄로 적는다(#278).

    예: (건넨 돈: 금화 10닢 → 영애)
        (건네려던 돈: 금화 10닢 → 영애. 돈이 모자랐다)
    """
    to = f' → {note.target}' if note.target else ''
    if not note.paid:
        return f'(건네려던 돈: {note.amount}{to}. {TRADE_FAILURES.get(note.reason, "하지 못했다")})'
    return f'(건넨 돈: {note.amount}{to})'


def describe_handed_over(notes: list[HandOverNote]) -> str:
    """
    이룬 퀘스트에 넘긴 물건들을 한 줄로 적는다. 퀘스트의 차례, 그 안의 물건 차례다.

    예: (넘긴 물건: 약초 배달에 약초 2개)
        (넘긴 물건: 약초 배달에 약초 2개, 편지 전하기에 편지 1개)
    """
    return '(넘긴 물건: ' + ', '.join(f'{note.quest}에 {note.name} {note.count}개' for note in notes) + ')'


def lost_before_acting(move: Move) -> str | None:
    """
    선언을 냈지만 차례가 오기 전에 죽거나 쓰러져 하지 못했으면 그 말. 아니면 None.

    앞사람의 치료가 실패해 그 자리에서 죽었거나, 앞 차례의 몬스터에게 쓰러졌다(app/rounds/judging.py 의 lost_turn).
    죽은 것은 그 칸(lost_turn)이 생기기 전에 굳힌 것도 알아본다. 판정과 지목의 결과가 없고 죽어 있으면 그렇다.
    """
    if not move.content:
        return None
    if move.dead and move.verdict is None and move.naming is None:
        return '(하려던 일을 하기 전에 죽었다)'
    if move.lost_turn == 'downed':
        return '(하려던 일을 하기 전에 쓰러졌다)'
    return None


def describe_move(move: Move) -> str:
    """
    한 캐릭터가 한 일을 한 줄로 적는다. 판정이 있었으면 뒤에 붙이고, 치료였으면 그 결과를,
    HP 가 바뀌었으면 그 뒤에 붙인다. 지목이었으면 그 결과를, 물건을 쓰거나 건넸으면 그 결과를 붙인다.
    죽음의 굴림을 굴렸으면 그 뒤에, 시간이 지나 나은 부상이 있으면 그 뒤에, 입고 있는 부상이 있으면 그 뒤에,
    가진 물건이 있으면 그 뒤에, 돈이 있는 판이면 가진 돈을 그 뒤에, 맵에 서 있으면 그 장소의 이름을 맨 뒤에 붙인다.
    맵에서 가거나 찾았으면 물건의 결과 자리에 그 결과를, 쉬었으면 그 뒤에 쉰 결과를 붙인다.
    되살아나기와 저절로 회복은 죽음의 굴림 뒤에 붙인다.
    서 있는 곳의 출구와 숨긴 길은 붙이지 않는다. 이 줄은 가짜 서술자가 장면으로 그대로 내보낸다(PlaceNote).
    """
    parts = [f'{move.character_name}: {move.content or describe_idle(move)}']
    lost = lost_before_acting(move)
    if lost is not None:
        parts.append(lost)
    if move.throw is not None:
        parts.append(describe_throw(move.throw))
    # 굴린 기술(#805 ②)도 판정 앞에 적는다. 던지기와 같다
    rolled_skill = move.skill is not None and move.skill.rolled
    if rolled_skill:
        parts.append(describe_skill(move.skill))
    # 인물이나 몬스터에게 쓴 물건(#800)은 판정 앞에 적는다. 던지기와 같다
    used_on = move.item_action is not None and move.verdict is not None
    if used_on:
        parts.append(describe_item_action(move.item_action))
    if move.verdict is not None:
        parts.append(describe_verdict(move.verdict))
        if move.verdict.treatment is not None:
            parts.append(describe_treatment(move.verdict.treatment))
        if move.verdict.impact is not None:
            parts.append(describe_impact(move.verdict.impact))
        if move.verdict.npc_impact is not None:
            parts.append(describe_npc_impact(move.verdict.npc_impact))
        if move.verdict.monster_impact is not None:
            parts.append(describe_npc_impact(move.verdict.monster_impact))
        if move.verdict.drop is not None:
            parts.append(describe_drop(move.verdict.drop))
        if move.verdict.wake is not None:
            parts.append(describe_wake(move.verdict.wake))
    if move.target_gone is not None:
        parts.append(describe_target_gone(move.target_gone))
    if move.naming is not None:
        parts.append(describe_naming(move.naming))
    if move.item_action is not None and not used_on:
        parts.append(describe_item_action(move.item_action))
    if move.skill is not None and not rolled_skill:
        parts.append(describe_skill(move.skill))
    if move.travel is not None:
        parts.append(describe_travel(move.travel))
    if move.search is not None:
        parts.append(describe_search(move.search))
    if move.door is not None:
        parts.append(describe_door(move.door))
    if move.take is not None:
        parts.append(describe_take(move.take))
    if move.put_down is not None:
        parts.append(describe_put_down(move.put_down))
    if move.trap_set is not None:
        parts.append(describe_trap_set(move.trap_set))
    if move.disarm is not None:
        parts.append(describe_disarm(move.disarm))
    if move.steal is not None:
        parts.append(describe_steal(move.steal))
    if move.loot is not None:
        parts.append(describe_loot(move.loot))
    if move.trade is not None:
        parts.append(describe_trade(move.trade))
    if move.pay is not None:
        parts.append(describe_pay(move.pay))
    if move.handed_over:
        parts.append(describe_handed_over(move.handed_over))
    if move.rest is not None:
        parts.append(describe_rest(move.rest))
    if move.wait is not None:
        parts.append(describe_wait(move.wait))
    if move.cover is not None:
        parts.append(describe_cover(move.cover))
    if move.wander is not None:
        parts.append(describe_wander(move.wander))
    if move.death_save is not None:
        parts.append(describe_death_save(move.death_save))
    if move.revival is not None:
        parts.append(describe_revival(move.revival))
    if move.recovery is not None:
        parts.append(describe_recovery(move.recovery))
    if move.healed:
        parts.append(describe_healed(move.healed))
    if move.injuries:
        parts.append(f'[입은 부상: {describe_injuries(move.injuries)}]')
    if move.items:
        parts.append(f'[소지품: {describe_items(move.items)}]')
    if move.money is not None:
        parts.append(f'[소지금: {move.money}]')
    if move.resources:
        parts.append(f'[수치: {", ".join(describe_resource(one) for one in move.resources)}]')
    if move.worn:
        parts.append(f'[착용: {describe_worn(move.worn)}]')
    if move.place is not None:
        parts.append(f'[있는 곳: {move.place.name}]')
    return ' '.join(parts)


# 겨눈 몬스터를 칠 수 없었던 까닭의 말
GONE_REASONS = {
    'dead': '이미 죽어 있었다',
    'elsewhere': '그 자리에 없었다',
    # 해치려던 동료(#803)
    'left': '자리를 떠났다',
    'downed': '이미 쓰러져 있었다',
    'friendly_fire_off': '동료를 해칠 수 없게 바뀌었다',
}


def describe_target_gone(note: TargetGoneNote) -> str:
    """
    겨눈 몬스터를 칠 수 없어 굴리지 않은 것을 적는다.

    예: (겨눈 상대 수로 쥐 2: 이미 죽어 있었다. 판정하지 않았다)
        (겨눈 상대: 그 자리에 없었다. 판정하지 않았다)
    """
    reason = GONE_REASONS.get(note.reason, GONE_REASONS['elsewhere'])
    who = f'겨눈 상대 {note.name}' if note.name else '겨눈 상대'
    return f'({who}: {reason}. 판정하지 않았다)'


def describe_monster_turn(note: MonsterTurnNote) -> str:
    """
    몬스터 한 마리나 싸우는 인물 하나의 차례를 한 줄로 적는다. 굴림의 숫자는 싣지 않는다.
    맞았으면 그 캐릭터의 HP 변화를 붙인다.

    예: 수로 쥐 2: 엘프에게 물기 (맞음) → 엘프 피해 3 (HP 7/10)
        수로 쥐 2: 엘프에게 물기 (빗나감)
        악역영애: 엘프에게 부채 후리기 (맞음) → 엘프 피해 2 (HP 8/10)
        수로 쥐 2: 쓰러진 엘프에게 물기 (맞음) → 엘프 죽음의 굴림 실패 +1 (실패 2/3, 죽어 가는 중)
        흑마법사: 엘프에게 화염구 (맞음) [마나 모자람] → 엘프 피해 5 (HP 5/10)   비용을 냈다(#805 ③-a)
        흑마법사: 엘프에게 화염구 (비용이 모자라 하지 못함)
        독거미: 엘프에게 독니 (맞음) → 엘프 피해 2 (HP 8/10) [입힌 부상: 중독] [수치: 마나 5 → 3/7]   효과(#805 ③-b)
    도감의 글(생김새, 약점)은 싣지 않는다. 가짜 서술자는 이 줄을 장면으로 그대로 내보낸다.
    """
    if note.short:
        return f'{note.name}: {note.target}에게 {note.attack} (비용이 모자라 하지 못함)'
    result = '맞음' if note.hit else '빗나감'
    target = note.target if note.downed is None else f'쓰러진 {note.target}'
    line = f'{note.name}: {target}에게 {note.attack} ({result})'
    if note.cost:
        line += f' [{", ".join(describe_resource(one) for one in note.cost)}]'
    if note.blow is not None:
        line += f' [{describe_blow(note.blow)}]'
    if note.impact is not None:
        line += f' {describe_impact(note.impact)}'
    if note.downed is not None and note.downed.added:
        line += f' {describe_downed_strike(note.target, note.downed)}'
    return ' '.join([line, *effect_tags([], note.injured, note.resisted), *resource_tags(note.resources)])


def describe_downed_strike(target: str, note: DownedStrikeNote) -> str:
    """
    쓰러진 캐릭터를 맞힌 결과를 줄 뒤에 붙일 글. 피해 대신 죽음의 굴림 실패가 쌓인다(#369).

    예: → 엘프 죽음의 굴림 실패 +2 (실패 3/3, 죽음)
    """
    return f'→ {target} 죽음의 굴림 실패 +{note.added} (실패 {note.failures}/{note.limit}, {FATES[note.fate]})'


def take_move(moves: list[Move], used: list[bool], name: str) -> Move | None:
    """아직 놓지 않은 한 일 중에서 이 캐릭터의 것을 찾아 놓은 것으로 표시한다. 없으면 None."""
    for index, move in enumerate(moves):
        if not used[index] and move.character_name == name:
            used[index] = True
            return move
    return None


def round_lines(moves: list[Move], turns: list[TurnNote]) -> list[str]:
    """
    이번 라운드에 한 일의 줄들. 차례가 있으면 차례 순서로 캐릭터와 몬스터와 인물의 줄을 섞는다.

    차례가 없으면(맞붙은 몬스터도 싸우는 인물도 없었으면) 한 일의 순서(앉은 순서) 그대로다.
    차례가 없는 캐릭터(행동 없는 선언, 선언을 내지 않음, 쓰러져 있음)의 줄은 차례들 뒤에 앉은 순서로 놓는다.
    가짜 서술자와 프롬프트가 함께 쓴다.
    """
    if not turns:
        return [describe_move(move) for move in moves]
    used = [False] * len(moves)
    lines = []
    for turn in turns:
        attack = turn.monster or turn.npc
        if attack is not None:
            lines.append(describe_monster_turn(attack))
            continue
        move = take_move(moves, used, turn.character_name)
        if move is not None:
            lines.append(describe_move(move))
    lines.extend(describe_move(move) for move, done in zip(moves, used, strict=True) if not done)
    return lines

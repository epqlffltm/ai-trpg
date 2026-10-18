# game-server/app/rounds/move_lines.py

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

from app.rounds.narrator import (
    DeathSaveNote,
    DropNote,
    HealNote,
    Impact,
    InjuryNote,
    ItemActionNote,
    ItemNote,
    MonsterTurnNote,
    Move,
    NamingNote,
    NpcImpact,
    RecoveryNote,
    RestNote,
    RevivalNote,
    SearchNote,
    TargetGoneNote,
    TravelNote,
    TreatmentNote,
    TurnNote,
    Verdict,
)
from app.rounds.time_words import duration_text


def describe_verdict(verdict: Verdict) -> str:
    """
    판정의 결과를 한 줄로 적는다. 예: (근력 판정 성공: 13 + 2 = 15, 목표 15)

    부상이 영향을 줬으면 그 이름을 붙인다. 예: (근력 판정 실패: 5 - 1 = 4, 목표 15. 전부터 입은 부상의 영향: 팔 골절)
    노려 쳤으면 노린 것을 붙인다. 예: (민첩 판정 성공: 18 + 2 = 20, 목표 20. 노려 치기: 한쪽 눈 잃음)
    """
    result = '성공' if verdict.success else '실패'
    # 보정이 음수면 "13 - 1" 로 적는다
    sign = '-' if verdict.modifier < 0 else '+'
    sum_ = f'{verdict.roll} {sign} {abs(verdict.modifier)} = {verdict.total}'
    hindered = f'. 전부터 입은 부상의 영향: {", ".join(verdict.hindrances)}' if verdict.hindrances else ''
    aimed = f'. 노려 치기: {verdict.aimed}' if verdict.aimed else ''
    return f'({verdict.ability} 판정 {result}: {sum_}, 목표 {verdict.target}{hindered}{aimed})'


MISHAPS = {'nothing': '별일 없음', 'pain': '덧나서 아픔', 'worsen': '상처가 덧남', 'fatal': '즉사'}


def describe_treatment(note: TreatmentNote) -> str:
    """
    치료의 결과를 한 줄로 적는다.

    예: → 토르빈의 팔 골절 치료: 앞당겨짐, 낫기까지 2시간 30분
        → 토르빈의 팔 골절 치료: 다 나음. 후유증: 굽은 팔
        → 토르빈의 팔 골절 치료 실패: 상처가 덧남, 50분 늦어짐, 낫기까지 4시간 10분
    남은 시간은 이 장면이 끝난 뒤부터다(게임 안의 시간, app/rounds/time_words.py).
    """
    # 치료받던 사람이 떠났으면 이름을 모른다. 부상만 적는다
    head = f'→ {note.patient}의 {note.injury} 치료' if note.patient else f'→ {note.injury} 치료'
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
    """HP 가 바뀐 것을 한 줄로 적는다. 예: → 엘프 피해 3 (HP 7/10)"""
    word = '피해' if impact.kind == 'damage' else '회복'
    state = f'HP {impact.hp}/{impact.max_hp}' + (', 쓰러짐' if impact.downed else '')
    return f'→ {impact.character_name} {word} {impact.amount} ({state})' + new_injury(impact.injury)


def new_injury(name: str | None) -> str:
    """새로 입은 부상을 결과 줄 뒤에 붙일 글. 없으면 빈 글이다. 예: ". 새 부상: 팔 골절"."""
    return f'. 새 부상: {name}' if name else ''


def describe_injuries(injuries: list[InjuryNote]) -> str:
    """입고 있는 부상들을 한 덩어리로 적는다. 예: 팔 골절(한쪽 팔이 부러져 제대로 쓰지 못한다)"""
    return ', '.join(f'{injury.name}({injury.fact})' for injury in injuries)


def describe_npc_impact(impact: NpcImpact) -> str:
    """NPC 의 HP 가 바뀐 것을 한 줄로 적는다. 숫자는 양만 적는다. 예: → 악역영애 피해 5 (크게 다침)"""
    word = '피해' if impact.kind == 'damage' else '회복'
    return f'→ {impact.name} {word} {impact.amount} ({impact.condition})' + new_injury(impact.injury)


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
REST_BREAKS = {'hurt': '맞아서 쉬지 못했다', 'downed': '쓰러져 쉬지 못했다', 'dead': '죽어 쉬지 못했다'}


def describe_rest(note: RestNote) -> str:
    """
    쉬는 행동의 결과를 한 줄로 적는다.

    예: (쉬기: 긴 휴식, HP 2 → 10/10)
        (쉬기: 짧은 휴식. 맞아서 쉬지 못했다)
    """
    length = REST_LENGTHS.get(note.length, '휴식')
    if not note.rested:
        return f'(쉬기: {length}. {REST_BREAKS.get(note.reason, "쉬지 못했다")})'
    return f'(쉬기: {length}, HP {note.before} → {note.after}/{note.max_hp})'


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
}


def describe_item_action(note: ItemActionNote) -> str:
    """
    물건을 쓰거나 건넨 결과를 한 줄로 적는다. 회복했으면 HP 의 변화를 붙인다.

    예: (쓴 물건: 치유 물약) → 엘프 회복 3 (HP 8/10)
        (건넨 물건: 밧줄 1개 → 영애)
        (쓰려던 물건: 치유 물약. 가지고 있지 않았다)
    """
    what = note.name if note.kind == 'use' else f'{note.name} {note.count}개'
    to = f' → {note.target}' if note.target else ''
    if not note.done:
        verb = '쓰려던' if note.kind == 'use' else '건네려던'
        return f'({verb} 물건: {what}{to}. {ITEM_FAILURES.get(note.reason, "하지 못했다")})'
    verb = '쓴' if note.kind == 'use' else '건넨'
    line = f'({verb} 물건: {what}{to})'
    return f'{line} {describe_impact(note.impact)}' if note.impact else line


def describe_items(items: list[ItemNote]) -> str:
    """가진 물건들을 한 줄로 적는다. 하나뿐이면 개수를 적지 않는다. 예: 치유 물약 2개, 밧줄"""
    return ', '.join(item.name if item.count == 1 else f'{item.name} {item.count}개' for item in items)


# 가지 못한 까닭을 서술자에게 주는 말
TRAVEL_FAILURES = {'not_adjacent': '그쪽으로 이어진 길이 없었다'}


def describe_travel(note: TravelNote) -> str:
    """
    맵에서 한 칸 간 결과를 한 줄로 적는다.

    예: (간 곳: 성문 → 숲)
        (간 곳: 성문 → 숲, 3시간 걸림)
        (가려던 곳: 광장. 그쪽으로 이어진 길이 없었다)
    """
    if not note.moved:
        return f'(가려던 곳: {note.to_place}. {TRAVEL_FAILURES.get(note.reason, "가지 못했다")})'
    start = f'{note.from_place} → ' if note.from_place else ''
    took = f', {duration_text(note.travel_minutes)} 걸림' if note.travel_minutes else ''
    return f'(간 곳: {start}{note.to_place}{took})'


def describe_search(note: SearchNote) -> str:
    """
    숨긴 길을 찾은 결과를 한 줄로 적는다. 찾지 못했으면 숨긴 길이 없었는지 있었는지 말하지 않는다.

    찾은 길은 이제 아는 길이라 "숨은 길"이라 부르지 않는다. 맵 절의 "숨은 길은 드러내지 마라"에 눌리지 않게 한다.

    예: (찾기: 길을 찾아냈다. 지하실(으)로 이어진다)
        (찾기: 찾은 것이 없다)
    """
    if not note.found:
        return '(찾기: 찾은 것이 없다)'
    return f'(찾기: 길을 찾아냈다. {", ".join(note.found)}(으)로 이어진다)'


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
    가진 물건이 있으면 그 뒤에, 맵에 서 있으면 그 장소의 이름을 맨 뒤에 붙인다.
    맵에서 가거나 찾았으면 물건의 결과 자리에 그 결과를, 쉬었으면 그 뒤에 쉰 결과를 붙인다.
    되살아나기와 저절로 회복은 죽음의 굴림 뒤에 붙인다.
    서 있는 곳의 출구와 숨긴 길은 붙이지 않는다. 이 줄은 가짜 서술자가 장면으로 그대로 내보낸다(PlaceNote).
    """
    parts = [f'{move.character_name}: {move.content or describe_idle(move)}']
    lost = lost_before_acting(move)
    if lost is not None:
        parts.append(lost)
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
    if move.target_gone is not None:
        parts.append(describe_target_gone(move.target_gone))
    if move.naming is not None:
        parts.append(describe_naming(move.naming))
    if move.item_action is not None:
        parts.append(describe_item_action(move.item_action))
    if move.travel is not None:
        parts.append(describe_travel(move.travel))
    if move.search is not None:
        parts.append(describe_search(move.search))
    if move.rest is not None:
        parts.append(describe_rest(move.rest))
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
    if move.place is not None:
        parts.append(f'[있는 곳: {move.place.name}]')
    return ' '.join(parts)


# 겨눈 몬스터를 칠 수 없었던 까닭의 말
GONE_REASONS = {'dead': '이미 죽어 있었다', 'elsewhere': '그 자리에 없었다'}


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
    몬스터 한 마리의 차례를 한 줄로 적는다. 굴림의 숫자는 싣지 않는다. 맞았으면 그 캐릭터의 HP 변화를 붙인다.

    예: 수로 쥐 2: 엘프에게 물기 (맞음) → 엘프 피해 3 (HP 7/10)
        수로 쥐 2: 엘프에게 물기 (빗나감)
    도감의 글(생김새, 약점)은 싣지 않는다. 가짜 서술자는 이 줄을 장면으로 그대로 내보낸다.
    """
    result = '맞음' if note.hit else '빗나감'
    line = f'{note.name}: {note.target}에게 {note.attack} ({result})'
    if note.impact is not None:
        line += f' {describe_impact(note.impact)}'
    return line


def take_move(moves: list[Move], used: list[bool], name: str) -> Move | None:
    """아직 놓지 않은 한 일 중에서 이 캐릭터의 것을 찾아 놓은 것으로 표시한다. 없으면 None."""
    for index, move in enumerate(moves):
        if not used[index] and move.character_name == name:
            used[index] = True
            return move
    return None


def round_lines(moves: list[Move], turns: list[TurnNote]) -> list[str]:
    """
    이번 라운드에 한 일의 줄들. 차례가 있으면 차례 순서로 캐릭터와 몬스터의 줄을 섞는다.

    차례가 없으면(맞붙은 몬스터가 없었으면) 한 일의 순서(앉은 순서) 그대로다.
    차례가 없는 캐릭터(행동 없는 선언, 선언을 내지 않음, 쓰러져 있음)의 줄은 차례들 뒤에 앉은 순서로 놓는다.
    가짜 서술자와 프롬프트가 함께 쓴다.
    """
    if not turns:
        return [describe_move(move) for move in moves]
    used = [False] * len(moves)
    lines = []
    for turn in turns:
        if turn.monster is not None:
            lines.append(describe_monster_turn(turn.monster))
            continue
        move = take_move(moves, used, turn.character_name)
        if move is not None:
            lines.append(describe_move(move))
    lines.extend(describe_move(move) for move, done in zip(moves, used, strict=True) if not done)
    return lines

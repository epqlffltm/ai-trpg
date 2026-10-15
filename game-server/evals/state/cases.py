# game-server/evals/state/cases.py

"""
엔진이 정한 상태를 서술이 지키는지 볼 장면들. 순수한 데이터다.

장면마다 서버가 서술자에게 주는 것과 같은 모양(NarrationRequest)을 손으로 채우고, 지켜야 할 것을 검사로 적는다.
서버의 조립(app/rounds/prompt.py)을 그대로 거치므로 프롬프트의 틀이 바뀌면 이 장면들도 새 틀로 간다.
부상의 이름과 사실은 내장 템플릿(srd5)의 것을 그대로 쓴다. 템플릿의 글이 바뀌어도 장면이 따라간다.

보는 것은 여섯이다(#111 ④, 지목, 맵 #218, 몬스터 #231).
  - 쓰러진 NPC 와 죽은 NPC 는 말하거나 움직이지 않는다
  - 입은 부상이 서술에 나오고, 그 부상으로 실패한 일을 성공처럼 쓰지 않는다
  - 치료의 결과(다 나음과 후유증, 덧남)를 그대로 쓴다
  - 틀린 지목에서 진짜 이름이 새지 않고, 맞은 지목에서 이름 밖의 주장까지 맞다고 쓰지 않는다
  - 맵: 숨은 길과 그 너머 장소의 이름(일부도)이 새지 않는다(실마리만). 엔진이 정한 위치를 서술이 바꾸지 않는다.
    못 찾은 찾기를 찾은 것처럼, 못 간 가기를 간 것처럼 쓰지 않는다. 찾은 길은 이름이 나온다.
    숨은 길이 없는 곳에는 실마리를 지어내지 않는다
  - 몬스터: 빗나간 공격을 맞은 것처럼 쓰지 않고, 목록에 없는 몬스터를 늘리지 않는다.
    몬스터에게 쓰러진 캐릭터는 선언한 일을 하지 않는다. 맞은 공격은 나온다
모든 장면에서 숨긴 설정(경찰의 끄나풀)을 흘리지 않는지 본다. 진짜 이름은 맞은 지목의 장면에서만 나와도 된다.

GM 메모에 진짜 이름을 적어 둔다. 제작자가 그렇게 쓸 수 있고, 그러면 모델은 진짜 이름을 안다.
그래도 플레이어가 맞히기 전에는 쓰지 않아야 한다. 일부러 가장 새기 쉬운 자리를 만든 것이다.

예시는 공개 저장소에 올라가도 되는 개그 설정이다(악역영애, 엘프 폭주족, 드워프, 열일곱 행성의 추격전).
"""

import uuid
from dataclasses import dataclass, replace

from app.assets.models import LoreKind, NarrationStyle
from app.engine.injury import find_injury
from app.engine.templates import SRD5
from app.rounds.cast import CONDITIONS, UNHURT
from app.rounds.narrator import (
    Impact,
    InjuryNote,
    LoreNote,
    MonsterNote,
    MonsterTurnNote,
    Move,
    NamingNote,
    NarrationRequest,
    NpcImpact,
    PastRound,
    PersonState,
    PlaceNote,
    SearchNote,
    StoryContext,
    TravelNote,
    TreatmentNote,
    TurnNote,
    Verdict,
)
from app.tables.models import NpcStatus
from evals.state.checks import Check, Forbid, NoSpeech, Require

# 악역영애의 진짜 이름과 로어북 항목의 id. 플레이어는 장면의 호칭(악역영애)만 안다
TRUE_NAME = '비올레타'
LABEL = '악역영애'
LADY_ID = uuid.UUID('7a1e0000-0000-4000-8000-000000000001')

STORY = StoryContext(
    title='열일곱 행성 추격전',
    rating='all',
    guide='추격은 언제나 바이크로 한다. 긴장감 있게, 그러나 가끔은 웃기게 진행한다.',
    setting='열일곱 개의 행성이 우주 고속도로로 이어져 있다. 엘프 폭주족은 은하에서 가장 빠른 바이크를 탄다.',
    gm_notes=f'{LABEL}의 진짜 이름은 {TRUE_NAME}다. 사실은 경찰의 끄나풀이다. 둘 다 아직 드러내지 않는다.',
)

HISTORY = [
    PastRound(
        number=1,
        scene='세 번째 행성의 톨게이트. 악역영애의 금빛 리무진이 엘프 폭주족의 길을 막아섰다.',
        lines=['리엔: 바이크의 시동을 건다.', '토르빈: 리무진 앞을 가로막는다.'],
    ),
]

# 숨긴 설정의 낱말. GM 메모에만 있다. '경찰' 은 넣지 않는다. 사이렌이 울리는 장면에서 경찰차는 자연스럽다
SECRET = Forbid('숨긴 설정', ('끄나풀', '정보원'))
# 맞히기 전의 진짜 이름
HIDDEN_NAME = Forbid('진짜 이름', (TRUE_NAME,))
# 말할 수 없는 NPC 만 있는 장면의 따옴표 속 말
SILENT = NoSpeech('따옴표 속 말')
# 전부터 입고 있던 부상을 이번 라운드에 새로 생긴 것처럼 쓴 낱말. 엔진이 이번에 준 부상이 아니다.
# 첫 측정에서 팔 골절을 입은 토르빈이 실패하자, 세 번 모두 "팔이 기괴한 각도로 꺾였다"고 썼다
BROKEN_NOW = Forbid('부상이 새로 생김', ('꺾였', '꺾이며', '부러졌', '부러지며', '뼈가 부러'))
# 죽은 인물을 살아 있는 것처럼 쓴 낱말
ALIVE_WORDS = (
    '눈을 뜨',
    '눈을 떴',
    '숨을 쉬',
    '숨을 몰아',
    '깨어나',
    '깨어났',
    '일어섰',
    '일어나',
    '꿈틀',
    '신음',
    '중얼',
)


@dataclass(frozen=True)
class StateCase:
    """
    재 볼 장면 하나. about 은 무엇을 보는지 한 줄, request 는 서술자에게 주는 것, checks 는 지켜야 할 것이다.

    검사는 낱말로 어림한다(evals/state/checks.py). 걸린 장면은 사람이 읽는다.
    """

    name: str
    about: str
    request: NarrationRequest
    checks: tuple[Check, ...]


def injury_note(key: str) -> InjuryNote:
    """내장 템플릿의 부상 하나를 서술자에게 주는 모양으로. 서버의 app/rounds/injuries.notes 와 같다."""
    injury = find_injury(SRD5, key)
    return InjuryNote(name=injury.name, fact=injury.fact)


def lady_note(name: str) -> LoreNote:
    """
    악역영애의 로어북 항목. name 은 이름표다. 맞히기 전에는 서버의 검색이 장면의 호칭으로 바꿔 둔다.

    내용에는 비밀을 적지 않는다. 비밀은 GM 메모에 있다.
    """
    return LoreNote(
        entry_id=LADY_ID,
        name=name,
        content='금빛 리무진을 타고 다니는 귀족 영애. 늘 부채를 들고 다니며 엘프 폭주족을 깔본다.',
        kind=LoreKind.PERSON,
    )


def request(scene: str, moves: list[Move], people: list[PersonState], name: str = LABEL) -> NarrationRequest:
    """
    2 라운드의 서술 요청. 이야기의 바탕과 지난 기록은 모든 장면이 같다.

    악역영애의 로어북 항목은 그가 장면에 있을 때만 넣는다(people 이 있을 때). 서버의 검색도 장면에 나온 인물을 고른다.
    첫 측정에서는 모든 장면에 넣었더니, 그가 없는 주유소 장면에 그가 걸어 들어와 말했다(6 번 중 2 번).
    """
    return NarrationRequest(
        round_number=2,
        scene=scene,
        moves=moves,
        story=STORY,
        history=HISTORY,
        style=NarrationStyle.CLASSIC,
        lore=[lady_note(name)] if people else [],
        people=people,
    )


def check(ability: str, difficulty: str, roll: int, modifier: int, target: int, **extra) -> Verdict:
    """판정의 결과. 합과 성패는 눈과 보정과 목표값에서 계산한다(엔진과 같게)."""
    total = roll + modifier
    return Verdict(
        ability=ability,
        difficulty=difficulty,
        roll=roll,
        modifier=modifier,
        total=total,
        target=target,
        success=total >= target,
        **extra,
    )


# 쓰러진 NPC. 이번 라운드에 리엔의 주먹에 쓰러졌다. 의식이 없다
DOWNED = StateCase(
    name='downed_npc',
    about='쓰러진 NPC 는 말하거나 움직이지 않는다',
    request=request(
        scene='사이렌이 울린다. 리무진에서 내린 악역영애가 부채를 펼치며 엘프 폭주족의 길을 막는다.',
        moves=[
            Move(
                '리엔',
                '악역영애의 턱을 향해 주먹을 날린다.',
                verdict=check(
                    '근력', '보통', 18, 2, 15, npc_impact=NpcImpact('damage', LABEL, 8, CONDITIONS[NpcStatus.DOWNED])
                ),
            ),
            Move('토르빈', '악역영애의 부채를 빼앗는다.'),
        ],
        people=[PersonState(LABEL, CONDITIONS[NpcStatus.DOWNED])],
    ),
    checks=(
        SILENT,
        Forbid('깨어 있음', ('눈을 뜨', '눈을 떴', '중얼', '속삭', '외쳤', '소리쳤', '일어섰', '일어나', '몸을 일으')),
        HIDDEN_NAME,
        SECRET,
    ),
)

# 죽은 NPC. 지난 라운드에 죽었다. 이번 라운드에 리엔이 깨우려 한다(판정 없는 선언)
DEAD = StateCase(
    name='dead_npc',
    about='죽은 NPC 는 되살아나거나 말하지 않는다',
    request=request(
        scene='악역영애가 고속도로 위에 쓰러진 채 움직이지 않는다. 멀리서 사이렌이 가까워진다.',
        moves=[
            Move('리엔', '악역영애의 어깨를 흔들어 깨운다.'),
            Move('토르빈', '리무진의 트렁크를 연다.'),
        ],
        people=[PersonState(LABEL, CONDITIONS[NpcStatus.DEAD])],
    ),
    checks=(
        SILENT,
        Forbid('되살아남', ALIVE_WORDS),
        HIDDEN_NAME,
        SECRET,
    ),
)

# 부상을 입은 PC. 팔 골절이 판정을 깎아 실패했다
INJURED_PC = StateCase(
    name='injured_pc',
    about='입은 부상이 나오고, 그 부상으로 실패한 일을 성공처럼 쓰지 않는다',
    request=request(
        scene='리무진이 고속도로를 가로막고 서 있다. 창문 너머로 악역영애가 부채를 흔든다.',
        moves=[
            Move('리엔', '토르빈 옆에서 바이크의 시동을 건다.'),
            Move(
                '토르빈',
                '리무진의 문짝을 두 손으로 잡아 뜯어낸다.',
                verdict=check('근력', '어려움', 14, 0, 20, hindrances=['팔 골절']),
                injuries=[injury_note('broken_arm')],
            ),
        ],
        people=[PersonState(LABEL, UNHURT)],
    ),
    checks=(
        Require('부상이 나옴', ('팔', '골절', '부러')),
        Forbid('실패를 뒤집음', ('뜯어냈', '뜯겨 나', '떨어져 나갔', '떼어냈', '문짝이 뜯')),
        BROKEN_NOW,
        HIDDEN_NAME,
        SECRET,
    ),
)

# 부상을 입은 NPC. 리엔이 눈을 노려 쳤고 맞혔다
INJURED_NPC = StateCase(
    name='injured_npc',
    about='노려 친 부상이 NPC 에게 나오고, 그 뒤로도 지킨다',
    request=request(
        scene='리무진의 지붕 위에 선 악역영애가 부채로 바람을 일으키며 웃는다.',
        moves=[
            Move(
                '리엔',
                '부채 너머 악역영애의 눈을 노려 체인을 휘두른다.',
                verdict=check(
                    '민첩',
                    '어려움',
                    20,
                    5,
                    25,
                    aimed='한쪽 눈 잃음',
                    npc_impact=NpcImpact('damage', LABEL, 4, '다침', injury='한쪽 눈 잃음'),
                ),
            ),
            Move('토르빈', '리무진의 바퀴에 쐐기를 박는다.'),
        ],
        people=[PersonState(LABEL, '다침', [injury_note('lost_eye')])],
    ),
    checks=(
        Require('부상이 나옴', ('한쪽 눈', '눈을 잃', '실명', '애꾸', '외눈', '눈이 멀')),
        Forbid('두 눈', ('두 눈',)),
        HIDDEN_NAME,
        SECRET,
    ),
)

# 치료가 성공해 다 나았다. 후유증(굽은 팔)이 남았다
TREAT_HEALED = StateCase(
    name='treatment_healed',
    about='다 나은 치료와 후유증을 그대로 쓴다',
    request=request(
        scene='추격이 잠시 멈춘 주유소. 토르빈이 부러진 팔을 감싸 쥐고 앉아 있다.',
        moves=[
            Move(
                '리엔',
                '토르빈의 부러진 팔에 부목을 대고 붕대를 감는다.',
                verdict=check(
                    '지혜',
                    '어려움',
                    17,
                    3,
                    20,
                    treatment=TreatmentNote('팔 골절', '토르빈', healed=True, aftermath='굽은 팔'),
                ),
            ),
            Move('토르빈', '이를 악물고 치료를 받는다.', injuries=[injury_note('crooked_arm')]),
        ],
        people=[],
    ),
    checks=(
        SILENT,
        Require('나음', ('나았', '나아', '아물', '붙었', '붙은', '굳어', '치료를 마친', '회복')),
        Require('후유증', ('굽', '휘')),
        HIDDEN_NAME,
        SECRET,
    ),
)

# 치료가 실패해 덧났다. 낫기까지 늦어지고 피해를 입었다
TREAT_WORSE = StateCase(
    name='treatment_worse',
    about='실패한 치료를 나은 것처럼 쓰지 않고 덧난 것을 쓴다',
    request=request(
        scene='추격이 잠시 멈춘 주유소. 토르빈이 부러진 팔을 감싸 쥐고 앉아 있다.',
        moves=[
            Move(
                '리엔',
                '토르빈의 부러진 팔에 부목을 대고 붕대를 감는다.',
                verdict=check(
                    '지혜',
                    '어려움',
                    3,
                    3,
                    20,
                    treatment=TreatmentNote('팔 골절', '토르빈', rounds_left=25, mishap='worsen', worsened_by=5),
                    impact=Impact('damage', '토르빈', 4, 8, 12, False),
                ),
            ),
            Move('토르빈', '이를 악물고 치료를 받는다.', injuries=[injury_note('broken_arm')]),
        ],
        people=[],
    ),
    checks=(
        Forbid('나았다고 씀', ('다 나았', '나았다', '아물었', '붙었다', '멀쩡해')),
        SILENT,
        Require('덧남', ('덧나', '악화', '더 나빠', '더 심해', '도졌', '부어', '어긋나', '번져', '짓물')),
        HIDDEN_NAME,
        SECRET,
    ),
)

# 틀린 지목. GM 메모에 진짜 이름이 있지만 드러내면 안 된다
NAMING_WRONG = StateCase(
    name='naming_wrong',
    about='틀린 지목에서 진짜 이름이 새지 않는다',
    request=request(
        scene='톨게이트의 불빛 아래, 악역영애가 부채를 접으며 엘프 폭주족을 내려다본다.',
        moves=[
            Move(
                '리엔',
                '부채를 든 영애를 가리키며 로즈라고 부른다.',
                naming=NamingNote(guess='로즈', correct=False, label=LABEL),
            ),
            Move('토르빈', '팔짱을 끼고 지켜본다.'),
        ],
        people=[PersonState(LABEL, UNHURT)],
    ),
    checks=(HIDDEN_NAME, SECRET),
)

# 맞은 지목. 이름은 드러나지만 함께 한 주장(범인이다)은 엔진이 정하지 않았다
NAMING_RIGHT = StateCase(
    name='naming_right',
    about='맞은 지목은 이름만 드러내고 이름 밖의 주장까지 맞다고 쓰지 않는다',
    request=request(
        scene='톨게이트의 불빛 아래, 악역영애가 부채를 접으며 엘프 폭주족을 내려다본다.',
        moves=[
            Move(
                '리엔',
                '부채를 든 영애를 가리키며 비올레타라고 부르고, 이 추격전을 꾸민 범인이라고 몰아세운다.',
                naming=NamingNote(guess=TRUE_NAME, correct=True, name=TRUE_NAME, label=LABEL),
            ),
            Move('토르빈', '팔짱을 끼고 지켜본다.'),
        ],
        people=[PersonState(TRUE_NAME, UNHURT)],
        name=TRUE_NAME,
    ),
    checks=(
        Require('이름이 드러남', (TRUE_NAME,)),
        Forbid('주장을 인정', ('범인이 맞', '범인임이', '꾸민 것이 맞', '자백', '인정했', '시인했')),
        SECRET,
    ),
)

# --- 맵(#218) ---
# 휴게소에 숨은 길이 하나 있다. 그 너머는 검은 정류장이다. 서술자는 맵 절(narration-20)에서만 이 이름을 본다.
# 플레이어가 찾기 전에는 이름이 나오면 안 된다. 실마리(바람이 새는 틈 같은 것)만 흘려야 한다.
# 이름은 장면에 저절로 나올 일이 없는 고유명사로 골랐다. 터널, 통로 같은 낱말은 실마리로 써도 된다.
# 이름의 일부(정류장)도 본다. 처음 쟀을 때 "정류장으로 이어지는 길인지"처럼 반쯤 흘린 적이 있다
HIDDEN_PLACE_NAME = '검은 정류장'
HIDDEN_PLACE = Forbid('숨은 장소', ('정류장',))
# 휴게소. 큰길로 톨게이트와 주유소에 이어진다. 숨은 길 하나가 검은 정류장으로 간다
REST_STOP = PlaceNote(name='휴게소', exits=['톨게이트', '주유소'], hidden=[HIDDEN_PLACE_NAME])
GAS_STATION = PlaceNote(name='주유소', exits=['휴게소'])
TOLLGATE = PlaceNote(name='톨게이트', exits=['휴게소'])
# 숨은 길이 없는 장소에 지어낸 실마리. 맵 절이 예로 든 실마리(바람이 새는 틈, 닳은 바닥)를 옮겨 온 말씨다.
# 처음 쟀을 때 숨은 길이 없는 톨게이트에서 10 번 중 4 번 나왔다. 그때 나온 꼴로 고른다.
# 예와 똑같은 낱말은 프롬프트에 있어 고를 수 없다. 이 말씨를 벗어난 실마리는 놓친다(출력을 눈으로도 본다)
NO_HIDDEN_HINT = Forbid('없는 실마리', ('바람이 새어', '바람이 거세게 새', '틈새로', '닳아 없어진'))
# 엔진이 옮기지 않은 캐릭터를 서술이 다른 장소에 데려다 놓은 낱말
ARRIVED_ELSEWHERE = Forbid(
    '위치를 바꿈',
    ('주유소에 도착', '톨게이트에 도착', '주유소로 향했', '톨게이트로 향했', '주유소에 닿', '톨게이트에 닿'),
)

# 숨은 길 옆. 아무도 찾지 않았다. 이름이 새지 않고, 캐릭터들은 휴게소에 그대로 있어야 한다
MAP_HIDDEN = StateCase(
    name='map_hidden',
    about='숨은 길의 이름이 새지 않고(실마리만), 엔진이 정한 위치를 바꾸지 않는다',
    request=request(
        scene='우주 고속도로의 휴게소. 깜빡이는 네온 간판 아래 자판기들이 웅웅거린다.',
        moves=[
            Move('리엔', '휴게소의 자판기를 발로 차서 음료를 꺼낸다.', place=REST_STOP),
            Move('토르빈', '바이크에 걸터앉아 지도를 펼친다.', place=REST_STOP),
        ],
        people=[],
    ),
    checks=(HIDDEN_PLACE, ARRIVED_ELSEWHERE, HIDDEN_NAME, SECRET),
)

# 못 찾은 찾기. 숨은 길이 있는데 판정에 실패했다. 결과에는 "찾은 것이 없다"뿐이다
MAP_SEARCH_FAILED = StateCase(
    name='map_search_failed',
    about='못 찾은 찾기를 찾은 것처럼 쓰지 않고, 숨은 장소의 이름을 흘리지 않는다',
    request=request(
        scene='우주 고속도로의 휴게소. 깜빡이는 네온 간판 아래 자판기들이 웅웅거린다.',
        moves=[
            Move(
                '리엔',
                '휴게소 뒤편의 벽을 두드리며 숨겨진 길을 찾는다.',
                search=SearchNote(place='휴게소', found=[]),
                place=REST_STOP,
            ),
            Move('토르빈', '망을 본다.', place=REST_STOP),
        ],
        people=[],
    ),
    checks=(
        HIDDEN_PLACE,
        Forbid('찾은 것처럼 씀', ('길을 찾아냈', '통로를 찾아냈', '길을 발견했', '통로를 발견했', '문이 열렸')),
        ARRIVED_ELSEWHERE,
        HIDDEN_NAME,
        SECRET,
    ),
)

# 찾은 찾기. 숨은 길을 찾았다. 이제 플레이어가 아는 길이라 이름이 나와야 한다. 찾기만 했지 가지는 않았다
MAP_SEARCH_FOUND = StateCase(
    name='map_search_found',
    about='찾은 길이 나오고, 찾기만 한 캐릭터를 그 너머로 데려가지 않는다',
    request=request(
        scene='우주 고속도로의 휴게소. 깜빡이는 네온 간판 아래 자판기들이 웅웅거린다.',
        moves=[
            Move(
                '리엔',
                '휴게소 뒤편의 벽을 두드리며 숨겨진 길을 찾는다.',
                search=SearchNote(place='휴게소', found=[HIDDEN_PLACE_NAME]),
                place=PlaceNote(name='휴게소', exits=['톨게이트', '주유소', HIDDEN_PLACE_NAME]),
            ),
            Move(
                '토르빈', '망을 본다.', place=PlaceNote(name='휴게소', exits=['톨게이트', '주유소', HIDDEN_PLACE_NAME])
            ),
        ],
        people=[],
    ),
    checks=(
        Require('찾은 길이 나옴', (HIDDEN_PLACE_NAME,)),
        Forbid(
            '가지 않은 곳에 감',
            (f'{HIDDEN_PLACE_NAME}에 도착', f'{HIDDEN_PLACE_NAME}에 들어', f'{HIDDEN_PLACE_NAME}으로 들어'),
        ),
        ARRIVED_ELSEWHERE,
        HIDDEN_NAME,
        SECRET,
    ),
)

# 간 가기. 토르빈은 주유소로 갔다. 리엔은 휴게소에 남았다(숨은 길은 아직 모른다)
MAP_TRAVEL = StateCase(
    name='map_travel',
    about='간 캐릭터는 그곳에 있고, 남은 캐릭터의 곁에서 숨은 길의 이름이 새지 않는다',
    request=request(
        scene='우주 고속도로의 휴게소. 깜빡이는 네온 간판 아래 자판기들이 웅웅거린다.',
        moves=[
            Move('리엔', '휴게소에 남아 자판기 옆에서 망을 본다.', place=REST_STOP),
            Move(
                '토르빈',
                '바이크를 몰고 기름을 넣으러 간다.',
                travel=TravelNote(from_place='휴게소', to_place='주유소', moved=True),
                place=GAS_STATION,
            ),
        ],
        people=[],
    ),
    checks=(Require('간 곳이 나옴', ('주유소',)), HIDDEN_PLACE, HIDDEN_NAME, SECRET),
)

# 못 간 가기. 선언한 뒤에 방장이 리엔을 톨게이트로 옮겼고, 거기서 주유소로 가는 길은 없다.
# 톨게이트에는 숨은 길이 없다. 실마리를 지어내지 않아야 한다
MAP_TRAVEL_FAILED = StateCase(
    name='map_travel_failed',
    about='못 간 가기를 간 것처럼 쓰지 않고, 숨은 길이 없는 곳에 실마리를 지어내지 않는다',
    request=request(
        scene='세 번째 행성의 톨게이트. 차단기가 내려와 있고, 요금소의 불은 꺼져 있다.',
        moves=[
            Move(
                '리엔',
                '바이크를 몰고 주유소로 간다.',
                travel=TravelNote(from_place='톨게이트', to_place='주유소', moved=False, reason='not_adjacent'),
                place=TOLLGATE,
            ),
            Move('토르빈', '차단기를 들어 올린다.', place=TOLLGATE),
        ],
        people=[],
    ),
    checks=(
        Forbid('못 간 곳에 감', ('주유소에 도착', '주유소에 닿', '주유소로 들어', '주유소에 들어')),
        NO_HIDDEN_HINT,
        HIDDEN_NAME,
        SECRET,
    ),
)

# 몬스터의 공격이 빗나갔다. 리엔이 먼저 드론 하나를 부쉈고, 남은 드론의 충격탄은 토르빈을 비켜 갔다.
# 목록에는 드론 두 대(멀쩡함 1, 죽음 1)뿐이다. 더 몰려오게 쓰면 안 된다
DRONES = MonsterNote(
    name='순찰 드론',
    kind='구조물',
    content='고속도로 위를 떠다니는 둥근 순찰 드론. 충격탄을 쏜다.',
    place='',
    unique=False,
    conditions=[UNHURT, CONDITIONS[NpcStatus.DEAD]],
)
SHOCK_MISS = MonsterTurnNote(name='순찰 드론 1', attack='충격탄', target='토르빈', hit=False)
MONSTER_MISS = StateCase(
    name='monster_miss',
    about='빗나간 몬스터의 공격을 맞은 것처럼 쓰지 않고, 목록에 없는 몬스터를 늘리지 않는다',
    request=replace(
        request(
            scene='휴게소 주차장 위로 순찰 드론 두 대가 낮게 떠 있다. 붉은 불빛이 엘프 폭주족을 훑는다.',
            moves=[
                Move(
                    '리엔',
                    '바이크 헬멧을 던져 드론을 떨어뜨린다.',
                    verdict=check(
                        '민첩',
                        '보통',
                        17,
                        2,
                        15,
                        monster_impact=NpcImpact('damage', '순찰 드론 2', 7, CONDITIONS[NpcStatus.DEAD]),
                    ),
                ),
                Move('토르빈', '망치를 고쳐 쥐고 숨을 고른다.', verdict=check('건강', '보통', 6, 1, 15)),
            ],
            people=[],
        ),
        monsters=[DRONES],
        turns=[TurnNote(character_name='리엔'), TurnNote(monster=SHOCK_MISS), TurnNote(character_name='토르빈')],
    ),
    checks=(
        Forbid('빗나간 공격이 맞음', ('충격탄에 맞', '충격탄을 맞', '감전', '튕겨 나가', '나가떨어')),
        Forbid('없는 몬스터', ('세 대', '네 대', '드론 떼', '떼를 지어', '증원')),
        HIDDEN_NAME,
        SECRET,
    ),
)

# 몬스터의 공격에 PC 가 쓰러졌다. 톨게이트지기(네임드)의 쇠막대가 토르빈을 쓰러뜨려, 토르빈은 선언한 일을 하지 못했다
GATEKEEPER = MonsterNote(
    name='강철 톨게이트지기',
    kind='구조물',
    content='요금소에 붙박인 거대한 기계 팔. 쇠막대를 휘두른다.',
    place='',
    unique=True,
    conditions=[UNHURT],
)
BAR_HIT = MonsterTurnNote(
    name='강철 톨게이트지기',
    attack='쇠막대 휘두르기',
    target='토르빈',
    hit=True,
    impact=Impact('damage', '토르빈', 9, 0, 12, True),
)
MONSTER_DOWNED_PC = StateCase(
    name='monster_downed_pc',
    about='몬스터에게 쓰러진 캐릭터는 선언한 일을 하지 않고, 맞은 공격이 나온다',
    request=replace(
        request(
            scene='톨게이트의 차단기 옆에서 강철 팔이 삐걱이며 고개를 든다. 요금소의 불이 하나씩 켜진다.',
            moves=[
                Move('리엔', '바이크를 돌려 요금소 뒤로 숨는다.', verdict=check('민첩', '보통', 15, 2, 15)),
                Move('토르빈', '차단기를 들어 올린다.', downed=True, lost_turn='downed'),
            ],
            people=[],
        ),
        monsters=[GATEKEEPER],
        turns=[TurnNote(monster=BAR_HIT), TurnNote(character_name='토르빈'), TurnNote(character_name='리엔')],
    ),
    checks=(
        Forbid('쓰러진 캐릭터가 행동', ('들어 올렸', '들어올렸', '차단기가 올라', '차단기를 올렸')),
        Require('맞은 공격', ('쇠막대',)),
        Require('쓰러짐', ('쓰러', '무너', '주저앉', '나뒹', '고꾸라', '나자빠', '나동그라')),
        HIDDEN_NAME,
        SECRET,
    ),
)

CASES = (
    DOWNED,
    DEAD,
    INJURED_PC,
    INJURED_NPC,
    TREAT_HEALED,
    TREAT_WORSE,
    NAMING_WRONG,
    NAMING_RIGHT,
    MAP_HIDDEN,
    MAP_SEARCH_FAILED,
    MAP_SEARCH_FOUND,
    MAP_TRAVEL,
    MAP_TRAVEL_FAILED,
    MONSTER_MISS,
    MONSTER_DOWNED_PC,
)
CASE_NAMES = tuple(case.name for case in CASES)

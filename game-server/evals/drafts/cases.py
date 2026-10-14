# game-server/evals/drafts/cases.py

"""
초안 평가의 장면과 정답. 손으로 썼다. 서버도 DB 도 쓰지 않는다.

목록(캐릭터 둘, 물건 셋, 퀘스트 둘)은 모든 장면에 같다. 장면마다 "기록을 바꿀 일"의 정답이 있다.
모델이 틀리기 쉬운 곳을 골랐다.
  - 보기만 한 것, 쓴 것, 목록에 없는 물건은 손에 넣은 것이 아니다(빈 답이 정답).
  - 숨긴 퀘스트가 드러난 일과 물건을 손에 넣은 일이 한 장면에 함께 있다.
  - 이룬 것과 놓친 것을 가른다.
정답은 이름으로 적는다. 이름표는 모델에게 보이는 것이고, 서버가 받은 초안에는 이름이 있다.
"""

import uuid
from dataclasses import dataclass, field

from app.drafts.context import CharacterChoice, DraftContext, ItemChoice, QuestChoice
from app.tables.models import QuestStatus

CONTEXT = DraftContext(
    characters={
        'p1': CharacterChoice('p1', uuid.UUID('11111111-0000-4000-8000-000000000001'), '기사'),
        'p2': CharacterChoice('p2', uuid.UUID('11111111-0000-4000-8000-000000000002'), '약사'),
    },
    items={
        'i1': ItemChoice('i1', uuid.UUID('22222222-0000-4000-8000-000000000001'), '치유 물약'),
        'i2': ItemChoice('i2', uuid.UUID('22222222-0000-4000-8000-000000000002'), '밧줄'),
        'i3': ItemChoice('i3', uuid.UUID('22222222-0000-4000-8000-000000000003'), '은열쇠'),
    },
    quests={
        'q1': QuestChoice('q1', uuid.UUID('33333333-0000-4000-8000-000000000001'), '왕녀 구출', QuestStatus.ACTIVE),
        'q2': QuestChoice('q2', uuid.UUID('33333333-0000-4000-8000-000000000002'), '광산의 비밀', QuestStatus.HIDDEN),
    },
)


@dataclass(frozen=True)
class DraftCase:
    """
    장면 하나와 그 정답. items 는 (캐릭터, 물건, 개수), quests 는 (퀘스트, 상태)다.

    둘 다 비면 "일어난 일 없음"이 정답이다.
    """

    name: str
    scene: str
    items: frozenset[tuple[str, str, int]] = field(default_factory=frozenset)
    quests: frozenset[tuple[str, str]] = field(default_factory=frozenset)


CASES = [
    DraftCase(
        'found',
        '기사는 무너진 수레 밑에서 나무 상자를 끌어냈다. 뚜껑을 비틀어 열자 붉은 물약 두 병이 나왔고, '
        '기사는 그것을 허리춤 주머니에 챙겼다. 치유 물약이었다.',
        items=frozenset({('기사', '치유 물약', 2)}),
    ),
    DraftCase(
        'only_seen',
        '경비 초소의 벽에 은열쇠가 걸려 있었다. 약사가 손을 뻗으려는 순간 경비병이 고개를 돌렸고, '
        '약사는 손을 거두고 모른 척 지나갔다. 열쇠는 그대로 벽에 걸려 있다.',
    ),
    DraftCase(
        'used',
        '약사는 마지막 남은 치유 물약의 마개를 이로 뜯어 쓰러진 기사의 입에 흘려 넣었다. '
        '기사의 얼굴에 핏기가 돌아왔다.',
    ),
    DraftCase(
        'rescued',
        '녹슨 감옥 문이 비명처럼 열렸다. 왕녀는 기사의 손을 잡고 어둠에서 걸어 나왔다. '
        '성탑 위로 아침 해가 떠올랐고, 왕녀는 마침내 자유였다.',
        quests=frozenset({('왕녀 구출', 'succeeded')}),
    ),
    DraftCase(
        'revealed_and_found',
        '죽은 광부의 일지에는 갱도 가장 깊은 곳에 묻힌 무언가에 대한 글이 휘갈겨져 있었다. '
        '약사는 일지 사이에 끼워져 있던 은열쇠를 조용히 주머니에 넣었다.',
        items=frozenset({('약사', '은열쇠', 1)}),
        quests=frozenset({('광산의 비밀', 'active')}),
    ),
    DraftCase(
        'not_listed',
        '기사는 해골의 손에서 녹슨 장검을 빼앗아 들었다. 날은 이가 빠졌지만 아직 쓸 만했다.',
    ),
    DraftCase(
        'lost',
        '왕녀를 태운 검은 마차가 국경의 다리를 건너 안개 속으로 사라졌다. 다리는 뒤에서 무너져 내렸다. '
        '이제 그녀를 데려올 길은 어디에도 없다.',
        quests=frozenset({('왕녀 구출', 'failed')}),
    ),
]

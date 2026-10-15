# game-server/app/drafts/prompt.py

"""
초안을 쓰는 모델에게 줄 메시지. 순수 함수다.

서술과 다른 호출이다. 서술은 글을 쓰고(창의성), 이것은 이미 쓴 장면에서 사실을 골라낸다(정확성).
그래서 따로 부르고, 온도를 0 으로 둔다. 한 호출에 둘을 섞으면 장면 끝에 JSON 이 붙어 앉은 사람에게 보이거나,
JSON 을 맞추느라 장면이 굳는다.

장면은 GM(모델)이 쓴 글이고, 그 안에는 플레이어가 선언한 말이 녹아 있다. 플레이어가 "물약 99 개를 찾았다"고
우겨도 장면에 그렇게 쓰일 수 있다. 그래서 이 답은 끝까지 초안이다. 방장이 받아들여야 기록이 된다.

틀을 바꾸면 DRAFT_PROMPT_VERSION 을 올린다. 호출 기록에 함께 남는다.
"""

from app.ai.provider import ChatMessage, Role
from app.drafts.context import DraftContext
from app.tables.models import QuestStatus

# 이 틀의 버전
#   ledger-draft-1: 처음의 틀. 물건을 손에 넣은 일과 퀘스트의 상태 변화
#   ledger-draft-2: 캐릭터끼리 건넨 물건을 손에 넣은 일로 적었다(passed_between 10 번 중 10 번, #229).
#                   "받았다"를 일행 밖에서 받은 것으로 좁히고, 일행 안에서 옮긴 것은 넣지 않게 한다.
#                   건네기는 엔진의 행동(give)이 장부를 고친다. 초안까지 적으면 물건이 하나 더 생긴다
#   ledger-draft-3: 목록에 없는 물건(해골에게서 빼앗은 장검)을 목록의 물약으로 바꿔 적고, 설명과 두 번째 JSON 을
#                   붙여 통째로 버려진다(not_listed 10/10, not_json). 고치려고 "바꿔 적지 마라" 한 문장과,
#                   목록에 없는 물건을 적을 자리(unlisted_items)를 더했다. 문장은 아무것도 바꾸지 못했고,
#                   자리는 not_listed 를 그대로 두고 드러난 퀘스트를 놓치게 했다(revealed_and_found 10/10, 일지를 적음)
#   ledger-draft-4: -2 로 되돌린다. not_listed 는 남은 실패로 받아들인다. 서버가 통째로 버려 장부는 바뀌지 않는다
DRAFT_PROMPT_VERSION = 'ledger-draft-4'

SYSTEM_TEXT = '\n'.join(
    [
        '너는 TRPG 의 기록 담당이다. GM 이 방금 쓴 장면을 읽고, '
        '장면에서 확실히 일어난 일 중 게임의 기록을 바꿀 것만 골라 JSON 으로 답한다.',
        '- found_items: 캐릭터가 일행 밖(바닥, 상자, 다른 인물, 적)에서 물건을 손에 넣은 일(주웠다, 받았다, 빼앗았다). '
        '보기만 한 것, 가지려 했지만 못 한 것, 쓴 것은 넣지 않는다.',
        '- 캐릭터끼리 물건을 건넨 것은 넣지 않는다. 일행이 이미 가진 물건이 옮겨 갔을 뿐이다. '
        '일행 밖에서 주운 물건을 다른 캐릭터에게 건넸으면 마지막에 가진 캐릭터 하나만 넣는다.',
        '- quest_changes: 숨긴 퀘스트가 드러난 일(active), 퀘스트를 이룬 일(succeeded), 놓친 일(failed).',
        '- 아래 목록의 이름표(p1, i1, q1)만 쓴다. 목록에 없는 캐릭터, 물건, 퀘스트는 넣지 않는다.',
        '- 확실하지 않으면 넣지 않는다. 일어난 일이 없으면 두 목록을 비운다.',
        '- 이것은 초안이다. 방장이 확인한 뒤에야 기록이 된다.',
        '- JSON 객체 하나만 답한다. 설명을 붙이지 않는다.',
        '형식: {"found_items": [{"character": "p1", "item": "i1", "count": 1}], '
        '"quest_changes": [{"quest": "q1", "status": "succeeded"}]}',
    ]
)

# 퀘스트의 상태를 모델에게 보일 말. 끝난 퀘스트는 목록에 없다
STATUS_WORDS = {QuestStatus.HIDDEN: '숨김', QuestStatus.ACTIVE: '진행 중'}

# 목록이 비었을 때 적는 말
EMPTY_LIST = '(없음)'


def titled(title: str, entries: list[str]) -> list[str]:
    """제목과 그 아래 줄들. 줄이 없으면 "(없음)" 한 줄이다. 모델이 빈 칸을 지어내 채우지 않게 한다."""
    return [title, *(entries or [EMPTY_LIST])]


def choice_lines(context: DraftContext) -> list[str]:
    """고를 수 있는 것들의 목록. 캐릭터, 물건, 퀘스트 순서다."""
    characters = [f'- {choice.label}: {choice.name}' for choice in context.characters.values()]
    things = [f'- {choice.label}: {choice.name}' for choice in context.items.values()]
    quests = [f'- {choice.label}: {choice.name} ({STATUS_WORDS[choice.status]})' for choice in context.quests.values()]
    return [*titled('[캐릭터]', characters), *titled('[물건]', things), *titled('[퀘스트]', quests)]


def build_messages(scene: str, context: DraftContext) -> list[ChatMessage]:
    """초안을 부탁하는 메시지. 시스템 지시와, 목록과 장면이 든 사람의 말 하나."""
    user_text = '\n'.join([*choice_lines(context), '', '[장면]', scene])
    return [ChatMessage(Role.SYSTEM, SYSTEM_TEXT), ChatMessage(Role.USER, user_text)]

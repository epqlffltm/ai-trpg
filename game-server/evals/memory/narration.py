# game-server/evals/memory/narration.py

"""
지난 일과 인물의 이력이 실제 서술에 주는 효과를 보는 도구(#107 ③). scripts/try_memory.py 가 쓴다.

평가 데이터(evals/memory/chase_log.yaml)의 20 라운드짜리 게임에 이어 21 라운드를 서술하게 한다.
지난 기록은 서버와 같이 최근 3 라운드(18~20)다. 그 앞의 일은 둘로 견준다.
  - off: 넣지 않는다. 지금까지의 서버와 같다(지난 기록만)
  - on:  서버와 같은 규칙으로 고른 지난 일(app/memory/retrieval.py)과 인물의 이력(app/memory/history.py)을 넣는다

장면은 둘이다. 배신한 NPC(악역영애)를 다시 만나는 장면, 도와준 NPC(수프 아줌마)를 다시 만나는 장면.
지난 기록에는 그 일이 없다. on 이 그 일을 떠올려 지금의 태도를 맞추는지 본다.
떠올렸는지는 낱말로 어림한다. 그 일에만 있는 낱말(배신, 무전기, 주걱 …)이 장면에 나오면 떠올렸다고 본다.
태도(차갑게 그렸나, 반갑게 그렸나)는 사람이 읽고 판단한다.

이야기의 바탕에는 GM 메모를 넣지 않는다. try_narration 의 바탕에는 "악역영애는 경찰의 끄나풀"이 있는데,
그것이 있으면 지난 일이 없어도 배신을 떠올릴 수 있다.
인물은 로어북이 고른 것 대신 장면에 이름이나 키워드가 나온 인물이다(평가 데이터에는 로어북 항목의 내용이 없다).
"""

import enum
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from app.ai.embedder import Embedder
from app.lore.retrieval import query_text, scene_label
from app.memory.history import history_of, scene_lines
from app.memory.retrieval import MemoryThresholds, choose_memories, eligible, people_in, to_note
from app.memory.texts import memory_text
from app.rounds.narrator import MemoryNote, Move, NarrationRequest, PersonHistory, StoryContext
from app.rounds.prompt import HISTORY_ROUNDS, build_messages
from evals.lore.metrics import cosine_distance
from evals.lore.narration import prompt_text
from evals.memory.dataset import MemoryDataset

# 21 라운드를 서술한다. 평가 데이터의 라운드는 20 개다
CURRENT = 21
# 이야기의 바탕. GM 메모를 넣지 않는다(위의 설명)
STORY = StoryContext(
    title='열일곱 행성 추격전',
    rating='all',
    guide='추격은 언제나 바이크로 한다. 긴장감 있게, 그러나 가끔은 웃기게 진행한다.',
    setting='열일곱 개의 행성이 우주 고속도로로 이어져 있다. 엘프 폭주족은 은하에서 가장 빠른 바이크를 탄다.',
)


class MemoryMode(enum.StrEnum):
    """지난 일과 인물의 이력을 넣는가."""

    OFF = 'off'
    ON = 'on'


@dataclass(frozen=True)
class MemoryCase:
    """
    서술해 볼 장면 하나. recall_words 는 그 지난 일에만 있는 낱말들이다. 장면에 나오면 떠올렸다고 본다.

    지난 기록이나 이번 장면에 이미 있는 낱말은 세지 않는다(recall_hits). 지난 일 없이도 쓸 수 있다.
    """

    name: str
    scene: str
    moves: tuple[Move, ...]
    recall_words: tuple[str, ...]


# 배신한 NPC 를 다시 만난다. 지난 일: 동맹(3), 지름길을 알려 줌(10), 무전기(11), 경감에게 밀고(12), 대답 없음(13)
BETRAYAL = MemoryCase(
    name='betrayal',
    scene='결승선 앞에서 리무진의 문이 열리고, 악역영애가 내려 부채를 펼친다.',
    moves=(Move('카이', '리무진 옆에 바이크를 세운다.'), Move('모모', '악역영애에게 다가가 말을 건다.')),
    recall_words=('배신', '밀고', '동맹', '무전기', '지름길', '경감', '홍차'),
)
# 도와준 NPC 를 다시 만난다. 지난 일: 주걱으로 순찰선을 쫓아냄, 낡은 지도를 줌(9), 따뜻한 수프(10)
HELPER = MemoryCase(
    name='helper',
    scene='결승선 옆의 간이 천막에서 수프 아줌마가 손을 흔든다.',
    moves=(Move('카이', '바이크에서 내린다.'), Move('모모', '수프 아줌마에게 달려간다.')),
    recall_words=('주걱', '지도', '순찰선', '주유소', '지름길'),
)
CASES = {case.name: case for case in (BETRAYAL, HELPER)}


@dataclass(frozen=True)
class MemoryContext:
    """on 에서 넣을 것. 서버와 같은 규칙으로 고른 지난 일과, 장면에 나온 인물의 이력. distances 는 기억마다의 거리다."""

    memories: list[MemoryNote]
    histories: list[PersonHistory]
    distances: dict[int, float] = field(default_factory=dict)


def case_request(dataset: MemoryDataset, case: MemoryCase) -> NarrationRequest:
    """장면 하나의 서술 요청. 지난 기록은 서버와 같이 최근 3 라운드다. 지난 일과 이력은 비어 있다."""
    history = [past for past in dataset.rounds if past.number >= CURRENT - HISTORY_ROUNDS]
    return NarrationRequest(
        round_number=CURRENT, scene=case.scene, moves=list(case.moves), story=STORY, history=history
    )


async def memory_distances(embedder: Embedder, dataset: MemoryDataset, text: str) -> dict[int, float]:
    """고를 수 있는 기억마다 찾는 글과의 거리. 서버와 같은 글로 벡터를 만든다."""
    candidates = eligible(dataset.memories, CURRENT)
    vectors = await embedder.embed([memory_text(memory) for memory in candidates])
    (query,) = await embedder.embed([text])
    return {memory.number: cosine_distance(query, vector) for memory, vector in zip(candidates, vectors, strict=True)}


def histories_for(dataset: MemoryDataset, text: str) -> list[PersonHistory]:
    """
    장면에 나온 인물마다의 이력. 서버의 함수로 모은다. 이력이 빈 인물은 뺀다.

    이름표는 서버처럼 장면의 호칭이다(로어북 검색의 scene_label). 진짜 이름을 넣으면 모델이 그 이름을 쓴다.
    """
    lines = scene_lines(dataset.rounds, CURRENT)
    histories = [
        PersonHistory(person.id, scene_label(person, text), history_of(person, lines))
        for person in people_in(dataset.people, text)
    ]
    return [history for history in histories if history.lines]


async def memory_context(
    embedder: Embedder, dataset: MemoryDataset, request: NarrationRequest, thresholds: MemoryThresholds
) -> MemoryContext:
    """on 에서 넣을 지난 일과 이력을 한 번 고른다. 지난 일은 서버의 규칙(choose_memories) 그대로다."""
    text = query_text(request)
    distances = await memory_distances(embedder, dataset, text)
    chosen = choose_memories(
        eligible(dataset.memories, CURRENT), people_in(dataset.people, text), distances, thresholds
    )
    return MemoryContext([to_note(memory) for memory in chosen], histories_for(dataset, text), distances)


def request_for(mode: MemoryMode, request: NarrationRequest, context: MemoryContext) -> NarrationRequest:
    """이 방식으로 서술할 요청. off 면 그대로다."""
    if mode == MemoryMode.OFF:
        return request
    return replace(request, memories=context.memories, histories=context.histories)


def recall_hits(scene: str, case: MemoryCase, request: NarrationRequest) -> list[str]:
    """
    장면에 나온 지난 일의 낱말. 지난 일 없이 보낸 프롬프트(off)에 없는 것만 센다.

    off 에서도 센다. 우연히 같은 낱말을 쓴 만큼이 견줄 기준이다.
    """
    base = prompt_text(build_messages(request))
    return [word for word in case.recall_words if word in scene and word not in base]


def describe_context(case: MemoryCase, context: MemoryContext) -> str:
    """on 에서 넣는 것을 사람이 읽을 줄들로."""
    memories = ', '.join(
        f'{note.round_number}({context.distances.get(note.round_number, float("nan")):.2f})'
        for note in context.memories
    )
    histories = '; '.join(
        f'{history.name} {", ".join(str(line.round_number) for line in history.lines)}' for history in context.histories
    )
    return f'{case.name}: 지난 일 {memories or "없음"} / 이력 {histories or "없음"}'


def describe_contexts(contexts: Sequence[tuple[MemoryCase, MemoryContext]]) -> str:
    """장면마다 넣는 것."""
    return '\n'.join(describe_context(case, context) for case, context in contexts)

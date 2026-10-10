# game-server/tests/test_lore_narration.py

"""
로어북이 서술에 주는 효과를 보는 도구(evals/lore/narration.py, scripts/try_narration.py 의 --lore)를 검증한다.

모델을 부르지 않는다. 임베딩은 가짜이거나 거리를 손으로 적는다. 서술은 가짜 provider 가 정해진 글을 돌려준다.
"""

import uuid

import pytest

from app.ai.fake import FakeEmbedder, FakeProvider
from app.ai.provider import ChatMessage, Reasoning, Role
from app.assets.models import NarrationStyle
from app.assets.scenarios.snapshot import EntrySnapshot
from app.lore.retrieval import Thresholds, choose, keyword_hits, query_text
from app.rounds import prompt
from evals.lore.dataset import entry_id, load_dataset
from evals.lore.narration import (
    NOISE_NAMES,
    LoreMode,
    LoreSets,
    describe_sets,
    entry_distances,
    lore_only_words,
    lore_sets,
    notes_for,
    prompt_text,
    select_noise,
    stem,
    used_words,
    words_of,
)
from scripts.try_narration import REQUEST, describe, run_trial, summarize


def entry(name: str, content: str = '', keywords: list[str] | None = None) -> EntrySnapshot:
    """이름에서 id 를 만든 항목."""
    return EntrySnapshot(id=entry_id(name), name=name, keywords=keywords or [], content=content)


LIEN = entry('리엔', '은빛 머리를 휘날리며 바이크를 몬다.', ['엘프'])
TUNNEL = entry('블랙홀 터널', '들어가면 시간이 거꾸로 흐른다.', ['블랙홀'])


# --- 낱말 ---


@pytest.mark.parametrize(
    ('word', 'expected'),
    [
        ('리무진을', '리무진'),
        ('경찰의', '경찰'),
        ('정비공이다', '정비공'),
        ('행성에서', '행성'),
        ('차는', '차는'),
        ('이', '이'),
    ],
)
def test_one_ending_is_cut_when_two_letters_stay(word: str, expected: str):
    assert stem(word) == expected


def test_words_are_hangul_stems_of_two_letters_or_more():
    assert words_of('리엔이 은빛 머리를 휘날리며 3번 달린다. OK') == {'리엔', '은빛', '머리', '휘날리며', '달린'}


def test_lore_only_words_are_the_ones_the_prompt_does_not_have():
    base = '리엔이 바이크를 탄다.'

    # 리엔, 바이크는 프롬프트에 있다. 키워드(엘프)는 세지 않는다
    assert lore_only_words([LIEN], base) == {'은빛', '머리', '휘날리며', '몬다'}


def test_used_words_are_the_ones_in_the_scene():
    assert used_words('은빛 머리가 흩날린다', {'머리', '은빛', '시간'}) == ['머리', '은빛']


def test_the_prompt_text_joins_every_message():
    messages = [ChatMessage(Role.SYSTEM, '규칙'), ChatMessage(Role.USER, '장면')]

    assert prompt_text(messages) == '규칙\n장면'


# --- 고르기 ---


def test_noise_entries_are_picked_by_name_in_order():
    entries = [LIEN, TUNNEL, entry('얼음 결정'), entry('별빛 연료')]

    assert [item.name for item in select_noise(entries)] == list(NOISE_NAMES)


def test_a_missing_noise_entry_is_an_error():
    with pytest.raises(ValueError, match='블랙홀 터널'):
        select_noise([LIEN])


def test_the_noise_entries_are_in_the_data_and_unrelated_to_the_example_round():
    entries = load_dataset().entries
    noise = select_noise(entries)

    # 예시 라운드의 글에 이름도 키워드도 나오지 않는다. 검색이 키워드로 고를 수 없다
    assert not set(keyword_hits(noise, query_text(REQUEST)))


async def test_distances_are_measured_for_every_entry():
    embedder = FakeEmbedder()

    distances = await entry_distances(embedder, [LIEN, TUNNEL], '리엔이 은빛 바이크를 몬다')

    assert set(distances) == {LIEN.id, TUNNEL.id}
    assert distances[LIEN.id] < distances[TUNNEL.id]


async def test_a_failing_embedder_gives_no_distances():
    assert await entry_distances(FakeEmbedder(error='unreachable'), [LIEN], '리엔') == {}


async def test_the_on_entries_are_chosen_by_the_server_rule():
    entries = load_dataset().entries
    embedder = FakeEmbedder()
    loose = Thresholds(max_distance=0.7, keyword_max_distance=2.0)

    sets = await lore_sets(embedder, entries, REQUEST, loose)

    text = query_text(REQUEST)
    expected = choose(entries, text, await entry_distances(embedder, entries, text), loose)
    assert sets.on == expected
    assert '리엔' in {item.name for item in sets.on}
    assert [item.name for item in sets.noise] == list(NOISE_NAMES)


async def test_without_distances_the_on_entries_are_keyword_hits():
    entries = load_dataset().entries

    sets = await lore_sets(FakeEmbedder(error='unreachable'), entries, REQUEST)

    assert sets.distances == {}
    assert {'리엔', '토르빈', '비올레타'} <= {item.name for item in sets.on}


def test_notes_follow_the_mode():
    sets = LoreSets(on=[LIEN], noise=[TUNNEL], distances={})

    assert notes_for(LoreMode.OFF, sets) == []
    assert [note.name for note in notes_for(LoreMode.ON, sets)] == ['리엔']
    assert [note.name for note in notes_for(LoreMode.NOISE, sets)] == ['블랙홀 터널']


def test_the_sets_are_described_with_their_distances():
    sets = LoreSets(on=[LIEN], noise=[TUNNEL], distances={LIEN.id: 0.412})

    assert describe_sets(sets) == 'on: 리엔(0.41)\nnoise: 블랙홀 터널'
    assert '키워드로만' in describe_sets(LoreSets(on=[], noise=[TUNNEL], distances={}))


# --- 서술해 보기 ---

SCENE = '리엔이 은빛 머리를 휘날리며 부채를 낚아챈다. 시간이 거꾸로 흐르는 듯하다.'


async def test_the_on_mode_puts_the_entries_in_the_prompt_and_counts_their_words():
    provider = FakeProvider(reply=SCENE)
    sets = LoreSets(on=[LIEN], noise=[TUNNEL], distances={})

    trial = await run_trial(provider, Reasoning.NONE, NarrationStyle.CLASSIC, False, LoreMode.ON, sets)

    (call,) = provider.calls
    last = call.messages[-1].content
    assert last.startswith(prompt.LORE_TITLE)
    assert f'- 리엔: {LIEN.content}' in last
    assert trial.lore == LoreMode.ON
    assert trial.notes == 1
    assert '휘날리며' in trial.lore_used
    # 상관없는 항목의 낱말에 끌려간 것도 함께 센다. 조사를 떼는 어림이라 '거꾸로' 는 '거꾸' 로 센다
    assert set(trial.noise_used) == {'시간', '거꾸'}


async def test_the_off_mode_sends_no_lore_but_still_counts_as_a_baseline():
    provider = FakeProvider(reply=SCENE)
    sets = LoreSets(on=[LIEN], noise=[TUNNEL], distances={})

    trial = await run_trial(provider, Reasoning.NONE, NarrationStyle.CLASSIC, False, LoreMode.OFF, sets)

    (call,) = provider.calls
    assert prompt.LORE_TITLE not in prompt_text(call.messages)
    assert trial.notes == 0
    # 넣지 않아도 우연히 같은 낱말을 쓸 수 있다. off 의 수가 견줄 기준이다
    assert '휘날리며' in trial.lore_used


async def test_without_lore_sets_nothing_is_counted():
    provider = FakeProvider(reply=SCENE)

    trial = await run_trial(provider, Reasoning.NONE, NarrationStyle.CLASSIC)

    assert (trial.lore, trial.notes, trial.lore_used, trial.noise_used) == (LoreMode.OFF, 0, (), ())


async def test_the_report_shows_the_lore_mode_and_the_word_counts():
    sets = LoreSets(on=[LIEN], noise=[TUNNEL], distances={})
    trial = await run_trial(
        FakeProvider(reply=SCENE), Reasoning.NONE, NarrationStyle.CLASSIC, False, LoreMode.NOISE, sets
    )

    assert '/ 로어북 noise /' in describe(trial)
    assert '넣은 항목 1개' in describe(trial)
    assert '| noise |' in summarize([trial])


def test_entry_ids_in_the_sets_are_the_data_ids():
    entries = load_dataset().entries

    assert all(isinstance(item.id, uuid.UUID) for item in select_noise(entries))

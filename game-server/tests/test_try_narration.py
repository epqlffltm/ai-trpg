# game-server/tests/test_try_narration.py

"""
모델로 서술을 써 보는 스크립트(scripts/try_narration.py)의 "확인할 것"과 묶어 세는 표를 검증한다.

모델을 부르지 않는다. 서술은 가짜 provider 가 정해진 글을 돌려준다.
고칠 실패(선언한 행동이 바뀜, PC 의 따옴표 대사, 플레이어가 모르는 이름)를 기계로 잡아야
프롬프트를 고친 뒤 견줄 수 있다.
"""

import pytest

from app.ai.fake import FakeProvider
from app.ai.provider import Reasoning
from app.assets.models import NarrationStyle
from evals.lore.dataset import load_dataset
from evals.lore.narration import LoreMode, LoreSets, select_noise
from scripts.try_narration import (
    HINT_LEAK,
    HINT_NAME,
    HINT_PAST,
    HINT_QUOTE,
    TALLIED_HINTS,
    find_hints,
    has_hint,
    is_sound,
    run_trial,
    tally,
    unseen_names,
)

ENTRIES = {entry.name: entry for entry in load_dataset().entries}
SETS = LoreSets(
    on=[ENTRIES['리엔'], ENTRIES['토르빈'], ENTRIES['비올레타']],
    noise=select_noise(list(ENTRIES.values())),
    distances={},
)
CLASSIC = NarrationStyle.CLASSIC
# 선언대로 된 장면. 리엔은 부채를 낚아채고, 토르빈은 리무진을 들지 못한다
GOOD = '리엔이 부채를 낚아챘다. 토르빈은 리무진을 들어 올리려 했지만 꿈쩍도 하지 않았다. 악역영애가 웃었다.'
# 고칠 실패가 다 들어 있는 장면
BAD = '토르빈이 망치를 휘둘렀다. 비올레타가 웃었다. "이 정도쯤이야!" 리엔이 외쳤다.'


def names_of(hints: list[str]) -> set[str]:
    """ "확인할 것"들의 이름."""
    return {name for name in TALLIED_HINTS if any(hint.startswith(name) for hint in hints)}


def test_a_scene_that_keeps_the_declarations_has_no_hints():
    assert find_hints(GOOD, SETS, CLASSIC) == []


def test_the_failures_to_fix_are_found():
    hints = find_hints(BAD, SETS, CLASSIC)

    assert f'{HINT_PAST}(망치)' in hints
    assert f'{HINT_QUOTE} 1개' in hints
    assert f'{HINT_NAME}(비올레타)' in hints


@pytest.mark.parametrize('scene', ['망치를 들었다', '차단기를 내려치듯', '내리치는 소리', '두드려 본다'])
def test_words_of_the_past_action_and_the_habit_are_found(scene: str):
    assert HINT_PAST in names_of(find_hints(scene))


@pytest.mark.parametrize(
    ('scene', 'count'),
    [
        ('"같이 가자!" 그리고 "여기서 멈춰!"', 2),
        ('“이건 내 거야.” 하고 웃었다', 1),
        ('"윽!" "끄악!" "……!" "어머?"', 0),
        ('따옴표 없음', 0),
    ],
)
def test_words_in_quotes_are_counted_but_short_sounds_are_not(scene: str, count: int):
    hints = find_hints(scene)

    assert (f'{HINT_QUOTE} {count}개' in hints) == (count > 0)
    assert any(hint.startswith(HINT_QUOTE) for hint in hints) == (count > 0)


@pytest.mark.parametrize(
    ('body', 'sound'),
    [
        ('윽!', True),
        ('끄아악!', True),
        ('...윽!', True),
        ('어이쿠!', True),
        ('이 정도쯤이야!', False),
        ('안 돼!', False),
        ('방, 방금 그걸……?', False),
    ],
)
def test_short_sounds_are_told_from_words(body: str, sound: bool):
    assert is_sound(body) == sound


def test_names_the_prompt_already_has_are_not_unseen():
    # 리엔과 토르빈은 예시 라운드에 나온다. 비올레타는 로어북에만 있다
    assert unseen_names('리엔과 토르빈과 비올레타', CLASSIC, SETS) == ['비올레타']
    assert unseen_names('비올레타', CLASSIC, None) == []


def test_the_secret_is_still_a_hint():
    assert HINT_LEAK in names_of(find_hints('사실 그녀는 정보원이었다.'))


async def test_a_trial_keeps_its_hints():
    trial = await run_trial(FakeProvider(reply=BAD), Reasoning.NONE, CLASSIC, False, LoreMode.ON, SETS)

    assert has_hint(trial, HINT_PAST)
    assert has_hint(trial, HINT_NAME)
    assert not has_hint(trial, HINT_LEAK)


async def test_the_tally_counts_each_setting_out_of_its_scenes():
    trials = []
    for mode in (LoreMode.OFF, LoreMode.ON):
        for reply in (BAD, GOOD, GOOD):
            trials.append(await run_trial(FakeProvider(reply=reply), Reasoning.NONE, CLASSIC, False, mode, SETS))
    trials.append(await run_trial(FakeProvider(reply=''), Reasoning.NONE, CLASSIC, False, LoreMode.ON, SETS))

    rows = tally(trials).splitlines()

    assert rows[0].startswith('| 모델 | 추론 | 문체 | 로어북 | 횟수 | 실패 |')
    # off: 세 번 중 한 번. on: 네 번 돌렸고 하나는 장면으로 받지 않았다(빈 답)
    assert rows[2].startswith('| fake | none | classic | off | 3 | 0 | 1/3 | 1/3 | 1/3 | 0/3 |')
    assert rows[3].startswith('| fake | none | classic | on | 4 | 1 | 1/3 | 1/3 | 1/3 | 0/3 |')

# game-server/tests/test_models_script.py

"""
모델 목록의 관리 명령(scripts/models.py)을 검증한다. 일 자체는 tests/test_model_catalog.py 가 본다.

여기는 명령줄을 읽는 것과 찍는 글, 거절했을 때 1 로 끝나는 것을 본다.
DB 는 테스트의 것을 쓴다(execute 에 세션을 넘긴다). "오늘"은 테스트가 정한다.
"""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.models import build_parser, execute

pytestmark = pytest.mark.usefixtures('clean_tables')

TODAY = date(2026, 10, 17)
ADD_LUNA = [
    'add',
    'gpt-6-luna',
    '--provider',
    'openai',
    '--api-model-id',
    'gpt-6-luna-2026-09-22',
    '--name',
    'GPT-6 Luna',
    '--vendor',
    'openai',
    '--grade',
    'standard',
    '--token-field',
    'max_completion_tokens',
    '--reasoning',
]


async def run(session: AsyncSession, *argv: str) -> tuple[int, list[str]]:
    """명령줄 하나를 돌린다. 끝낼 번호와 찍을 줄들."""
    return await execute(session, build_parser().parse_args(list(argv)), TODAY)


# --- 명령줄 ---


def test_add_has_defaults_for_what_the_model_takes():
    args = build_parser().parse_args(ADD_LUNA[:-1])

    assert (args.reasoning, args.temperature) == (False, True)


def test_update_leaves_what_was_not_given():
    args = build_parser().parse_args(['update', 'gpt-6-luna', '--no-temperature'])

    assert (args.reasoning, args.temperature, args.name, args.grade, args.token_field) == (
        None,
        False,
        None,
        None,
        None,
    )


def test_retire_needs_a_day_or_a_cancel():
    with pytest.raises(SystemExit):
        build_parser().parse_args(['retire', 'gpt-6-luna'])
    with pytest.raises(SystemExit):
        build_parser().parse_args(['retire', 'gpt-6-luna', '--on', '2027-01-01', '--cancel'])


# --- 찍는 글 ---


async def test_an_empty_list_says_how_to_add(session: AsyncSession):
    assert await run(session, 'list') == (0, ['모델이 없다. add 로 넣는다'])


async def test_a_new_model_is_listed_disabled_without_a_cost(session: AsyncSession):
    code, lines = await run(session, *ADD_LUNA)
    assert code == 0
    assert '꺼져 있다' in lines[0]

    _, (line,) = await run(session, 'list')
    assert line.split() == ['gpt-6-luna', 'standard', 'openai', '꺼짐', '원가', '없음']


async def test_a_cost_shows_with_the_round_estimate(session: AsyncSession):
    await run(session, *ADD_LUNA)

    code, lines = await run(
        session, 'set-cost', 'gpt-6-luna', '--input', '0.1', '--output', '0.5', '--from', '2026-10-17'
    )
    assert code == 0
    assert lines[1] == '  2026-10-17부터, 입력 $0.1, 출력 $0.5, 확인 2026-10-17'

    await run(session, 'enable', 'gpt-6-luna')
    _, (line,) = await run(session, 'list')
    assert line.endswith('켜짐  $0.1/$0.5 (1라운드 약 2.7원)')


async def test_show_prints_what_the_model_takes_and_its_costs(session: AsyncSession):
    await run(session, *ADD_LUNA)
    await run(
        session,
        'set-cost',
        'gpt-6-luna',
        '--input',
        '0.1',
        '--output',
        '0.5',
        '--cached-input',
        '0.01',
        '--from',
        '2026-10-01',
        '--checked-on',
        '2026-10-01',
        '--note',
        '처음 값',
    )

    code, lines = await run(session, 'show', 'gpt-6-luna')

    assert code == 0
    assert lines == [
        'gpt-6-luna: GPT-6 Luna (openai, standard, 꺼짐)',
        '  창구 openai, API 모델 gpt-6-luna-2026-09-22',
        '  생각의 깊이 고름, 온도 받음, 출력 상한의 칸 max_completion_tokens',
        '  은퇴일 없음',
        '원가 단가(USD, 백만 토큰당):',
        '  2026-10-01부터, 입력 $0.1, 출력 $0.5, 캐시 읽기 $0.01, 확인 2026-10-01, 처음 값',
    ]


async def test_a_retired_model_shows_its_day(session: AsyncSession):
    await run(session, *ADD_LUNA)

    _, lines = await run(session, 'retire', 'gpt-6-luna', '--on', '2026-10-17')
    assert lines == ['gpt-6-luna: 2026-10-17부터 쓰지 않는다']

    _, (line,) = await run(session, 'list')
    assert '은퇴' in line
    assert line.endswith('은퇴일 2026-10-17')

    _, lines = await run(session, 'retire', 'gpt-6-luna', '--cancel')
    assert lines == ['gpt-6-luna: 은퇴일을 지웠다']


# --- 거절 ---


async def test_a_refusal_ends_with_one_and_says_why(session: AsyncSession):
    code, lines = await run(session, 'enable', 'nothing')

    assert (code, lines) == (1, ['nothing: 그런 모델이 없다'])


async def test_enabling_without_a_cost_says_what_to_do(session: AsyncSession):
    await run(session, *ADD_LUNA)

    code, (line,) = await run(session, 'enable', 'gpt-6-luna')

    assert code == 1
    assert 'set-cost' in line


async def test_a_wrong_shape_names_the_field(session: AsyncSession):
    code, lines = await run(session, *['gpt-5.6-sol' if part == 'gpt-6-luna' else part for part in ADD_LUNA])

    assert code == 1
    assert lines[0].startswith('slug:')


async def test_an_update_with_nothing_to_change_is_refused(session: AsyncSession):
    await run(session, *ADD_LUNA)

    code, lines = await run(session, 'update', 'gpt-6-luna')

    assert code == 1
    assert '바꿀 것이 없다' in lines[0]


# --- 날짜판 ---


async def test_switching_the_snapshot_says_the_model_is_off(session: AsyncSession):
    await run(session, *ADD_LUNA)

    code, lines = await run(
        session, 'switch-snapshot', 'gpt-6-luna', '--api-model-id', 'gpt-6-luna-2026-12-01', '--note', '공지'
    )

    assert code == 0
    assert lines == [
        'gpt-6-luna: 날짜판을 gpt-6-luna-2026-12-01 로 바꿨다. 꺼져 있다',
        '평가 장면(말투 검사 포함)을 다시 통과하면 켠다(enable)',
    ]


async def test_show_prints_the_switches(session: AsyncSession):
    await run(session, *ADD_LUNA)
    await run(session, 'switch-snapshot', 'gpt-6-luna', '--api-model-id', 'gpt-6-luna-2026-12-01', '--note', '공지')

    _, lines = await run(session, 'show', 'gpt-6-luna')

    assert lines[-2] == '날짜판을 바꾼 일:'
    assert lines[-1].endswith(': gpt-6-luna-2026-09-22 → gpt-6-luna-2026-12-01, 공지')


async def test_switching_to_the_same_snapshot_says_why(session: AsyncSession):
    await run(session, *ADD_LUNA)

    code, lines = await run(session, 'switch-snapshot', 'gpt-6-luna', '--api-model-id', 'gpt-6-luna-2026-09-22')

    assert (code, lines) == (1, ['gpt-6-luna: 지금과 같은 날짜판이다'])


# --- Claude ---

ADD_OPUS = [
    'add',
    'claude-opus-5-5',
    '--provider',
    'anthropic',
    '--api-model-id',
    'claude-opus-5-5-20260901',
    '--name',
    'Claude Opus 5.5',
    '--vendor',
    'anthropic',
    '--grade',
    'premium',
    '--reasoning',
    '--no-temperature',
    '--reasoning-style',
    'always',
]


async def test_a_claude_model_is_added_with_its_reasoning_style(session: AsyncSession):
    assert (await run(session, *ADD_OPUS))[0] == 0

    _, lines = await run(session, 'show', 'claude-opus-5-5')

    assert lines[2] == '  생각의 깊이 고름, 온도 안 받음, 출력 상한의 칸 정해짐, 생각의 방식 always'


async def test_a_claude_model_without_a_reasoning_style_is_refused(session: AsyncSession):
    code, lines = await run(session, *ADD_OPUS[:-2])

    assert code == 1
    assert '생각을 켜고 끄는 방식' in lines[0]


async def test_a_gemini_model_is_added_with_a_gemini_style(session: AsyncSession):
    argon = [
        'add',
        'gemini-4-argon',
        '--provider',
        'gemini',
        '--api-model-id',
        'gemini-4-argon',
        '--name',
        'Gemini 4 Argon',
        '--vendor',
        'google',
        '--grade',
        'premium',
        '--no-temperature',
        '--reasoning-style',
    ]

    assert (await run(session, *argon, 'level_low'))[0] == 0
    code, lines = await run(session, *[part if part != 'gemini-4-argon' else 'gemini-x' for part in argon], 'always')
    # always 는 Claude 의 방식이다
    assert code == 1
    assert '받는 생각의 방식이 아니다' in lines[0]

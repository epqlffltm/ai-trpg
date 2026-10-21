# trpg-server/tests/test_models_script.py

"""
모델 목록의 관리 명령(scripts/models.py)을 검증한다. 들여오기 자체는 tests/test_catalog_sync.py,
켜고 끄기와 원가는 tests/test_model_catalog.py 가 본다.

여기는 명령줄을 읽는 것과 찍는 글, 거절했을 때 1 로 끝나는 것을 본다.
DB 는 테스트의 것을 쓴다(execute 에 세션을 넘긴다). "오늘"은 테스트가 정한다.
파일은 테스트가 임시 폴더에 쓴다(sync --file). 들여오기만 하는 테스트는 설치된 ai-core 의 파일도 읽어 본다.
"""

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.models import build_parser, execute

pytestmark = pytest.mark.usefixtures('empty_catalog')

TODAY = date(2026, 10, 17)
LUNA = """
[[models]]
slug = "gpt-6-luna"
provider = "openai"
api_model_id = "{api_model_id}"
display_name = "GPT-6 Luna"
vendor = "openai"
grade = "standard"
supports_reasoning = true
token_limit_field = "max_completion_tokens"
{retires}

[[models.costs]]
effective_from = 2026-10-01
checked_on = 2026-10-01
input_per_mtok = 0.1
cached_input_per_mtok = 0.01
output_per_mtok = 0.5
note = "처음 값"
"""
OPUS = """
[[models]]
slug = "claude-opus-5-5"
provider = "anthropic"
api_model_id = "claude-opus-5-5-20260901"
display_name = "Claude Opus 5.5"
vendor = "anthropic"
grade = "premium"
supports_reasoning = true
supports_temperature = false
reasoning_style = "always"
"""


def catalog_text(*models: str) -> str:
    """판과 모델들로 된 파일의 글."""
    return 'format = 1\n' + ''.join(models)


def luna(api_model_id: str = 'gpt-6-luna-2026-09-22', retires_on: str | None = None) -> str:
    """파일의 Luna."""
    return LUNA.format(api_model_id=api_model_id, retires=f'retires_on = {retires_on}' if retires_on else '')


def write(tmp_path: Path, text: str, name: str = 'catalog.toml') -> str:
    """파일을 쓰고 그 경로를 글로."""
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return str(path)


async def run(session: AsyncSession, *argv: str) -> tuple[int, list[str]]:
    """명령줄 하나를 돌린다. 끝낼 번호와 찍을 줄들."""
    return await execute(session, build_parser().parse_args(list(argv)), TODAY)


async def sync(session: AsyncSession, tmp_path: Path, *models: str, dry_run: bool = False) -> tuple[int, list[str]]:
    """그 모델들의 파일을 들여온다."""
    argv = ['sync', '--file', write(tmp_path, catalog_text(*models))]
    return await run(session, *argv, *(['--dry-run'] if dry_run else []))


# --- 명령줄 ---


def test_sync_reads_the_bundled_file_unless_told():
    args = build_parser().parse_args(['sync'])

    assert (args.file, args.dry_run) == (None, False)


@pytest.mark.parametrize('command', ['add', 'update', 'set-cost', 'switch-snapshot', 'retire'])
def test_the_commands_the_file_replaced_are_gone(command: str):
    # 모델과 원가, 날짜판, 은퇴일은 파일을 고쳐 들여온다
    with pytest.raises(SystemExit):
        build_parser().parse_args([command, 'gpt-6-luna'])


# --- 들여오기 ---


async def test_sync_says_what_it_added_and_what_to_do_next(session: AsyncSession, tmp_path: Path):
    code, lines = await sync(session, tmp_path, luna())

    assert code == 0
    assert lines == [
        'gpt-6-luna: 넣었다. 꺼져 있다. 평가 장면을 통과하면 켠다(enable)',
        'gpt-6-luna: 2026-10-01부터의 단가를 더했다',
    ]


async def test_a_second_sync_changes_nothing(session: AsyncSession, tmp_path: Path):
    await sync(session, tmp_path, luna())

    assert await sync(session, tmp_path, luna()) == (0, ['바뀐 것이 없다'])


async def test_sync_says_what_it_changed(session: AsyncSession, tmp_path: Path):
    await sync(session, tmp_path, luna(), OPUS)

    code, lines = await sync(session, tmp_path, luna('gpt-6-luna-2026-12-01', retires_on='2027-06-01'))

    assert code == 0
    assert lines == [
        'gpt-6-luna: 날짜판을 gpt-6-luna-2026-09-22 → gpt-6-luna-2026-12-01 로 바꿨다. 꺼져 있다. '
        '평가 장면(말투 검사 포함)을 다시 통과하면 켠다(enable)',
        'gpt-6-luna: retires_on 를 고쳤다',
        'claude-opus-5-5: 파일에 없다. 지우지 않고 그대로 둔다',
    ]


async def test_a_dry_run_says_so_and_keeps_the_table(session: AsyncSession, tmp_path: Path):
    code, lines = await sync(session, tmp_path, luna(), dry_run=True)

    assert code == 0
    assert lines[-1] == '미리 보기다. 표는 그대로다'
    assert await run(session, 'list') == (0, ['모델이 없다. sync 로 모델 목록의 파일을 들여온다'])


async def test_the_bundled_file_can_be_previewed(session: AsyncSession):
    code, lines = await run(session, 'sync', '--dry-run')

    assert code == 0
    assert lines[-1] == '미리 보기다. 표는 그대로다'
    assert any(line.startswith('claude-opus-5-5: 넣었다') for line in lines)


# --- 찍는 글 ---


async def test_an_empty_list_says_how_to_fill_it(session: AsyncSession):
    assert await run(session, 'list') == (0, ['모델이 없다. sync 로 모델 목록의 파일을 들여온다'])


async def test_a_new_model_is_listed_disabled(session: AsyncSession, tmp_path: Path):
    await sync(session, tmp_path, luna(), OPUS)

    _, lines = await run(session, 'list')

    assert [line.split() for line in lines] == [
        ['claude-opus-5-5', 'premium', 'anthropic', '꺼짐', '원가', '없음'],
        ['gpt-6-luna', 'standard', 'openai', '꺼짐', '$0.1/$0.5', '(1라운드', '약', '2.7원)'],
    ]


async def test_an_enabled_model_shows_the_round_estimate(session: AsyncSession, tmp_path: Path):
    await sync(session, tmp_path, luna())

    assert await run(session, 'enable', 'gpt-6-luna') == (0, ['gpt-6-luna: 켰다'])
    _, (line,) = await run(session, 'list')

    assert line.endswith('켜짐  $0.1/$0.5 (1라운드 약 2.7원)')


async def test_show_prints_what_the_model_takes_and_its_costs(session: AsyncSession, tmp_path: Path):
    await sync(session, tmp_path, luna())

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


async def test_show_prints_the_reasoning_style_and_the_switches(session: AsyncSession, tmp_path: Path):
    await sync(session, tmp_path, luna(), OPUS)
    await sync(session, tmp_path, luna('gpt-6-luna-2026-12-01'))

    _, opus = await run(session, 'show', 'claude-opus-5-5')
    _, switched = await run(session, 'show', 'gpt-6-luna')

    assert opus[2] == '  생각의 깊이 고름, 온도 안 받음, 출력 상한의 칸 정해짐, 생각의 방식 always'
    assert opus[-1] == '원가 단가가 없다'
    assert switched[-2] == '날짜판을 바꾼 일:'
    assert switched[-1].endswith(': gpt-6-luna-2026-09-22 → gpt-6-luna-2026-12-01')


async def test_a_retired_model_shows_its_day(session: AsyncSession, tmp_path: Path):
    await sync(session, tmp_path, luna(retires_on='2026-10-17'))

    _, (line,) = await run(session, 'list')

    assert '은퇴' in line
    assert line.endswith('은퇴일 2026-10-17')


async def test_the_fallback_is_set_and_cleared(session: AsyncSession, tmp_path: Path):
    await sync(session, tmp_path, luna())

    assert await run(session, 'fallback', 'gpt-6-luna') == (0, ['gpt-6-luna: openai 의 대체 모델로 정했다'])
    _, (line,) = await run(session, 'list')
    assert line.endswith(' 대체')
    _, (cleared,) = await run(session, 'fallback', 'gpt-6-luna', '--cancel')
    assert cleared.startswith('gpt-6-luna: 대체 모델에서 뺐다')


# --- 거절 ---


async def test_a_refusal_ends_with_one_and_says_why(session: AsyncSession):
    code, lines = await run(session, 'enable', 'nothing')

    assert (code, lines) == (1, ['nothing: 그런 모델이 없다'])


async def test_enabling_without_a_cost_says_what_to_do(session: AsyncSession, tmp_path: Path):
    await sync(session, tmp_path, OPUS)

    code, (line,) = await run(session, 'enable', 'claude-opus-5-5')

    assert code == 1
    assert '파일에 단가를 적고 sync' in line


async def test_a_wrong_file_names_the_field_and_imports_nothing(session: AsyncSession, tmp_path: Path):
    wrong = OPUS.replace('"always"', '"adaptive-ish"')

    code, lines = await sync(session, tmp_path, luna(), wrong)

    assert code == 1
    assert lines[0] == '모델 목록의 파일이 틀렸다. 아무것도 들여오지 않았다'
    assert lines[1].startswith('models.1.reasoning_style:')
    assert await run(session, 'list') == (0, ['모델이 없다. sync 로 모델 목록의 파일을 들여온다'])


async def test_a_missing_file_is_refused(session: AsyncSession, tmp_path: Path):
    code, lines = await run(session, 'sync', '--file', str(tmp_path / 'nothing.toml'))

    assert code == 1
    assert lines[1].startswith('파일을 읽을 수 없다')


async def test_a_conflict_with_the_table_says_why(session: AsyncSession, tmp_path: Path):
    await sync(session, tmp_path, OPUS)

    moved = OPUS.replace('provider = "anthropic"', 'provider = "gemini"').replace('"always"', '"level_low"')

    # 파일의 모양은 맞지만 표의 창구와 다르다. 창구는 바꾸지 않는다
    assert await sync(session, tmp_path, moved) == (
        1,
        ['claude-opus-5-5: 창구는 바꾸지 않는다. 다른 창구로 부르려면 이름표를 새로 정한다'],
    )

# chat-server/scripts/models.py

"""
모델 목록을 다루는 관리 명령. 관리 화면이 생기기 전까지 이것으로 모델 목록을 들여오고, 켜고 끈다.

    uv run python -m scripts.models sync --dry-run
    uv run python -m scripts.models sync
    uv run python -m scripts.models sync --file ../shared/ai-core/src/ai_core/model_catalog.toml
    uv run python -m scripts.models list
    uv run python -m scripts.models list --on 2026-12-01
    uv run python -m scripts.models show gpt-6-luna
    uv run python -m scripts.models enable gpt-6-luna
    uv run python -m scripts.models disable gpt-6-luna
    uv run python -m scripts.models adult grok-5 --allow
    uv run python -m scripts.models adult grok-5 --forbid

chat-server 폴더에서 -m 으로 돌린다. 설정(.env)의 DB 를 쓴다. 서버를 띄우지 않아도 된다.

모델과 원가, 날짜판, 은퇴일의 원본은 파일 하나다(ai_core/model_catalog.toml, #499). 파일을 고치고 sync 로 들여온다.
--file 이 없으면 설치된 ai-core 에 든 파일이다. 고친 파일을 이미지를 다시 굽지 않고 미리 볼 때 --file 을 준다.
켜고 끄기와 성인 등급의 대화에 쓰기는 이 서버의 표에서 한다(enable, disable, adult).
게임 서버의 것(trpg-server/scripts/models.py)을 줄여 옮겼다. 회사의 대체 모델과 1라운드 어림이 없다.

일은 모두 app/catalog 의 함수가 한다(들여오기는 sync.py, 나머지는 service.py). 여기는 명령줄을 읽어 그 함수를 부르고,
결과를 글로 찍는 것만 한다. 나중에 관리 서버가 생기면 같은 함수를 관리 API 로 연다.

판매가(말 한 번에 몇 크레딧)는 여기서 정하지 않는다.
결제 서버의 가격표(billing-server 의 cmd/prices, chat.<이름표>.i0.o0)가 정한다.

API 키는 여기 적지 않는다. 키는 .env 에만 둔다.
"""

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from pathlib import Path

from ai_core.catalog_contract import is_offered, is_retired
from ai_core.catalog_file import CatalogFileError, load_catalog
from server_core.database import create_engine, create_session_factory
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import service
from app.catalog.errors import CatalogConflictError, ModelNotFoundError
from app.catalog.models import AiModel, AiModelCost, AiModelSnapshot
from app.catalog.sync import SyncReport, sync_catalog
from app.core.config import get_settings
from app.core.dependencies import utc_now

# 명령 하나. 세션, 읽은 명령줄, 오늘을 받아 찍을 줄들을 돌려준다
Command = Callable[[AsyncSession, argparse.Namespace, date], Awaitable[list[str]]]

# 명령이 거절되었을 때의 까닭들. 찍고 1 로 끝낸다
# 파일이 틀렸으면 틀린 곳마다 한 줄이다(CatalogFileError.problems)
REFUSALS = (CatalogFileError, ModelNotFoundError, CatalogConflictError)


def plain(value: Decimal) -> str:
    """단가를 뒤의 0 없이 쓴다(0.100000 → 0.1)."""
    return f'{value.normalize():f}'


def status_of(model: AiModel, today: date) -> str:
    """켜짐, 꺼짐, 은퇴 중 하나."""
    if is_retired(model, today):
        return '은퇴'
    return '켜짐' if is_offered(model, today) else '꺼짐'


def cost_text(cost: AiModelCost | None) -> str:
    """입력/출력 단가(USD, 백만 토큰당). 단가가 없으면 그렇다고 쓴다."""
    if cost is None:
        return '원가 없음'
    return f'${plain(cost.input_per_mtok)}/${plain(cost.output_per_mtok)}'


def model_line(model: AiModel, cost: AiModelCost | None, today: date) -> str:
    """목록의 한 줄."""
    retires = f' 은퇴일 {model.retires_on}' if model.retires_on else ''
    adult = ' 성인' if model.allows_adult else ''
    line = f'{model.slug:<28} {model.grade:<9} {model.vendor:<10} {status_of(model, today)}  {cost_text(cost)}'
    return f'{line}{retires}{adult}'


def cost_line(cost: AiModelCost) -> str:
    """단가 하나의 줄. 캐시 단가와 확인한 날, 덧붙인 말까지."""
    parts = [
        f'{cost.effective_from}부터',
        f'입력 ${plain(cost.input_per_mtok)}',
        f'출력 ${plain(cost.output_per_mtok)}',
    ]
    if cost.cached_input_per_mtok is not None:
        parts.append(f'캐시 읽기 ${plain(cost.cached_input_per_mtok)}')
    if cost.cache_write_per_mtok is not None:
        parts.append(f'캐시 쓰기 ${plain(cost.cache_write_per_mtok)}')
    parts.append(f'확인 {cost.checked_on}')
    if cost.note:
        parts.append(cost.note)
    return '  ' + ', '.join(parts)


def snapshot_line(snapshot: AiModelSnapshot) -> str:
    """날짜판을 바꾼 일 하나의 줄. 바꾼 날(UTC)과 앞뒤 이름, 덧붙인 말."""
    line = f'  {snapshot.changed_at.date()}: {snapshot.previous_api_model_id} → {snapshot.api_model_id}'
    return f'{line}, {snapshot.note}' if snapshot.note else line


def detail_lines(model: AiModel, costs: list[AiModelCost], snapshots: list[AiModelSnapshot], today: date) -> list[str]:
    """모델 하나를 자세히. 받는 것과 단가들, 날짜판을 바꾼 일들."""
    token_field = model.token_limit_field or '정해짐'
    reasoning_style = f', 생각의 방식 {model.reasoning_style}' if model.reasoning_style else ''
    return [
        f'{model.slug}: {model.display_name} ({model.vendor}, {model.grade}, {status_of(model, today)})',
        f'  창구 {model.provider}, API 모델 {model.api_model_id}',
        f'  생각의 깊이 {"고름" if model.supports_reasoning else "못 고름"}, '
        f'온도 {"받음" if model.supports_temperature else "안 받음"}, 출력 상한의 칸 {token_field}{reasoning_style}',
        f'  은퇴일 {model.retires_on or "없음"}, 성인 등급의 대화에 {"씀" if model.allows_adult else "안 씀"}',
        '원가 단가(USD, 백만 토큰당):' if costs else '원가 단가가 없다',
        *[cost_line(cost) for cost in costs],
        *(['날짜판을 바꾼 일:'] if snapshots else []),
        *[snapshot_line(snapshot) for snapshot in snapshots],
    ]


def report_lines(report: SyncReport, dry_run: bool) -> list[str]:
    """들여오기로 바뀐 것을 글로. 새 모델과 날짜판이 바뀐 모델은 켜기 전에 할 일을 함께 쓴다."""
    lines = [
        *[f'{slug}: 넣었다. 꺼져 있다. 평가 장면을 통과하면 켠다(enable)' for slug in report.added],
        *[
            f'{change.slug}: 날짜판을 {change.previous} → {change.current} 로 바꿨다. 꺼져 있다. '
            '평가 장면(말투 검사 포함)을 다시 통과하면 켠다(enable)'
            for change in report.switched
        ],
        *[f'{slug}: {", ".join(names)} 를 고쳤다' for slug, names in report.changed.items()],
        *[f'{slug}: {day}부터의 단가를 더했다' for slug, day in report.costs],
        *[f'{slug}: 파일에 없다. 지우지 않고 그대로 둔다' for slug in report.not_in_file],
    ]
    if report.is_empty():
        lines.append('바뀐 것이 없다')
    if dry_run:
        lines.append('미리 보기다. 표는 그대로다')
    return lines


async def sync_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """모델 목록의 파일을 들여온다."""
    report = await sync_catalog(session, load_catalog(args.file), dry_run=args.dry_run)
    return report_lines(report, args.dry_run)


async def list_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """모든 모델과 그날의 단가."""
    day = args.on or today
    entries = await service.list_entries(session, day)
    if not entries:
        return ['모델이 없다. sync 로 모델 목록의 파일을 들여온다']
    return [model_line(entry.model, entry.cost, day) for entry in entries]


async def show_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """모델 하나를 자세히."""
    detail = await service.show_model(session, args.slug)
    return detail_lines(detail.model, detail.costs, detail.snapshots, today)


async def enable_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """모델을 켠다."""
    model = await service.enable_model(session, args.slug, today)
    return [f'{model.slug}: 켰다']


async def disable_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """모델을 끈다."""
    model = await service.disable_model(session, args.slug)
    return [f'{model.slug}: 껐다']


async def adult_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """성인 등급의 대화에 쓰게 하거나 쓰지 않게 한다."""
    if args.allow:
        model = await service.allow_adult(session, args.slug)
        return [f'{model.slug}: 성인 등급의 대화에 쓴다']
    model = await service.forbid_adult(session, args.slug)
    return [f'{model.slug}: 성인 등급의 대화에 쓰지 않는다. 이 모델을 고른 성인 대화는 다시 고르게 된다']


COMMANDS: dict[str, Command] = {
    'sync': sync_command,
    'list': list_command,
    'show': show_command,
    'enable': enable_command,
    'disable': disable_command,
    'adult': adult_command,
}


def add_sync_parser(commands: argparse._SubParsersAction) -> None:
    """sync 의 명령줄."""
    sync = commands.add_parser('sync', help='모델 목록의 파일을 표에 들여온다. 새 모델은 꺼진 채 들어간다')
    sync.add_argument('--file', type=Path, help='들여올 파일. 없으면 설치된 ai-core 에 든 파일이다')
    sync.add_argument('--dry-run', action='store_true', help='바뀔 것만 보이고 표는 그대로 둔다')


def add_switch_parsers(commands: argparse._SubParsersAction) -> None:
    """enable, disable, adult 의 명령줄."""
    commands.add_parser('enable', help='켠다. 오늘의 원가가 있고 은퇴하지 않았어야 한다').add_argument('slug')
    commands.add_parser('disable', help='끈다. 지우지 않는다').add_argument('slug')
    adult = commands.add_parser(
        'adult', help='성인 등급의 대화에 쓸지 정한다. 공급자의 약관을 확인하고 성인 평가 장면을 통과한 뒤에 켠다'
    )
    adult.add_argument('slug')
    switch = adult.add_mutually_exclusive_group(required=True)
    switch.add_argument('--allow', action='store_true', help='쓴다')
    switch.add_argument('--forbid', action='store_true', help='쓰지 않는다')


def build_parser() -> argparse.ArgumentParser:
    """명령줄의 모양."""
    parser = argparse.ArgumentParser(description='모델 목록을 다룬다.')
    commands = parser.add_subparsers(dest='command', required=True)
    add_sync_parser(commands)
    listing = commands.add_parser('list', help='모든 모델과 오늘의 단가')
    listing.add_argument('--on', type=date.fromisoformat, help='이 날의 단가로 본다')
    commands.add_parser('show', help='모델 하나와 그 단가들').add_argument('slug')
    add_switch_parsers(commands)
    return parser


def refusal_lines(error: Exception) -> list[str]:
    """거절된 까닭을 찍을 줄로. 파일이 틀렸으면 틀린 곳마다 한 줄이다."""
    if isinstance(error, CatalogFileError):
        return ['모델 목록의 파일이 틀렸다. 아무것도 들여오지 않았다', *error.problems]
    return [str(error)]


async def execute(session: AsyncSession, args: argparse.Namespace, today: date) -> tuple[int, list[str]]:
    """명령 하나를 돌린다. 끝낼 번호(0 잘 됨, 1 거절됨)와 찍을 줄들을 돌려준다."""
    try:
        return 0, await COMMANDS[args.command](session, args, today)
    except REFUSALS as error:
        return 1, refusal_lines(error)


async def run(args: argparse.Namespace) -> int:
    """설정의 DB 에 붙어 명령을 돌리고 결과를 찍는다. 끝낼 번호를 돌려준다."""
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            code, lines = await execute(session, args, utc_now().date())
    finally:
        await engine.dispose()
    print('\n'.join(lines), file=sys.stderr if code else sys.stdout)
    return code


def main() -> None:
    """명령줄을 읽고 돌린다."""
    sys.exit(asyncio.run(run(build_parser().parse_args())))


if __name__ == '__main__':
    main()

# game-server/scripts/models.py

"""
모델 목록을 다루는 관리 명령. 관리 화면이 생기기 전까지 이것으로 모델을 넣고, 원가를 적고, 켜고 끈다.

    uv run python -m scripts.models list
    uv run python -m scripts.models show gpt-6-luna
    uv run python -m scripts.models add gpt-6-luna --provider openai --api-model-id <공식 문서의 날짜 붙은 이름> \\
        --name "GPT-6 Luna" --vendor openai --grade standard --token-field max_completion_tokens --reasoning
    uv run python -m scripts.models add claude-opus-5-5 --provider anthropic --api-model-id <공식 문서의 이름> \\
        --name "Claude Opus 5.5" --vendor anthropic --grade premium --reasoning --no-temperature \\
        --reasoning-style always
    uv run python -m scripts.models add gemini-4-argon --provider gemini --api-model-id gemini-4-argon \\
        --name "Gemini 4 Argon" --vendor google --grade premium --reasoning --no-temperature --reasoning-style level_low
    uv run python -m scripts.models set-cost gpt-6-luna --input 0.1 --output 0.5 --from 2026-10-17
    uv run python -m scripts.models update gpt-6-luna --no-temperature
    uv run python -m scripts.models switch-snapshot gpt-6-luna --api-model-id <새 날짜판> --note "공급자 공지"
    uv run python -m scripts.models enable gpt-6-luna
    uv run python -m scripts.models disable gpt-6-luna
    uv run python -m scripts.models retire gpt-6-luna --on 2027-06-01
    uv run python -m scripts.models retire gpt-6-luna --cancel

game-server 폴더에서 -m 으로 돌린다. 설정(.env)의 DB 를 쓴다. 서버를 띄우지 않아도 된다.

일은 모두 app/catalog/service.py 의 함수가 한다. 여기는 명령줄을 읽어 그 함수를 부르고, 결과를 글로 찍는 것만 한다.
나중에 관리 서버가 생기면 같은 함수를 관리 API 로 연다.

판매가(1인 1라운드에 몇 크레딧)는 여기서 정하지 않는다. 결제 서버의 가격표(billing-server 의 cmd/prices)가 정한다.
여기의 원가와 1라운드 어림은 판매가가 맞는지 볼 때 쓴다.

API 키는 여기 적지 않는다. 키는 .env 에만 둔다.
"""

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import service
from app.catalog.errors import CatalogConflictError, InvalidModelError, ModelNotFoundError
from app.catalog.models import AiModel, AiModelCost, AiModelSnapshot, Grade, Provider, ReasoningStyle, TokenLimitField
from app.catalog.rules import is_offered, is_retired, round_cost_usd
from app.catalog.schemas import CostCreate, ModelCreate, ModelUpdate, SnapshotSwitch
from app.core.config import get_settings
from app.core.database import create_engine, create_session_factory

# 1라운드 어림을 원으로 보일 때의 환율. 어림이다. 판매가를 정할 때 쓴 값과 같다(프로젝트 문서 model-pricing-plan)
KRW_PER_USD = 1500

# 명령 하나. 세션, 읽은 명령줄, 오늘을 받아 찍을 줄들을 돌려준다
Command = Callable[[AsyncSession, argparse.Namespace, date], Awaitable[list[str]]]

# 명령이 거절되었을 때의 까닭들. 찍고 1 로 끝낸다
REFUSALS = (ValidationError, ModelNotFoundError, CatalogConflictError, InvalidModelError)


def today_utc() -> date:
    """오늘(UTC)."""
    return datetime.now(UTC).date()


def plain(value: Decimal) -> str:
    """단가를 뒤의 0 없이 쓴다(0.100000 → 0.1)."""
    return f'{value.normalize():f}'


def status_of(model: AiModel, today: date) -> str:
    """켜짐, 꺼짐, 은퇴 중 하나."""
    if is_retired(model, today):
        return '은퇴'
    return '켜짐' if is_offered(model, today) else '꺼짐'


def cost_text(cost: AiModelCost | None) -> str:
    """입력/출력 단가와 1라운드 어림. 단가가 없으면 그렇다고 쓴다."""
    if cost is None:
        return '원가 없음'
    round_usd = round_cost_usd(cost)
    round_krw = round_usd * KRW_PER_USD
    return f'${plain(cost.input_per_mtok)}/${plain(cost.output_per_mtok)} (1라운드 약 {round_krw:.1f}원)'


def model_line(model: AiModel, cost: AiModelCost | None, today: date) -> str:
    """목록의 한 줄."""
    retires = f' 은퇴일 {model.retires_on}' if model.retires_on else ''
    fallback = ' 대체' if model.vendor_fallback else ''
    line = f'{model.slug:<28} {model.grade:<9} {model.vendor:<10} {status_of(model, today)}  {cost_text(cost)}'
    return f'{line}{retires}{fallback}'


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
        f'  은퇴일 {model.retires_on or "없음"}{", 회사의 대체 모델" if model.vendor_fallback else ""}',
        '원가 단가(USD, 백만 토큰당):' if costs else '원가 단가가 없다',
        *[cost_line(cost) for cost in costs],
        *(['날짜판을 바꾼 일:'] if snapshots else []),
        *[snapshot_line(snapshot) for snapshot in snapshots],
    ]


def create_of(args: argparse.Namespace) -> ModelCreate:
    """add 의 명령줄로 새 모델을 만든다. 모양이 틀리면 ValidationError."""
    return ModelCreate(
        slug=args.slug,
        provider=args.provider,
        api_model_id=args.api_model_id,
        display_name=args.name,
        vendor=args.vendor,
        grade=args.grade,
        supports_reasoning=args.reasoning,
        supports_temperature=args.temperature,
        token_limit_field=args.token_field,
        reasoning_style=args.reasoning_style,
    )


def update_of(args: argparse.Namespace) -> ModelUpdate:
    """update 의 명령줄로 바꿀 것을 만든다. 적지 않은 것은 그대로 둔다."""
    return ModelUpdate(
        display_name=args.name,
        vendor=args.vendor,
        grade=args.grade,
        supports_reasoning=args.reasoning,
        supports_temperature=args.temperature,
        token_limit_field=args.token_field,
        reasoning_style=args.reasoning_style,
    )


def cost_of(args: argparse.Namespace, today: date) -> CostCreate:
    """set-cost 의 명령줄로 새 단가를 만든다. 확인한 날을 적지 않으면 오늘이다."""
    return CostCreate(
        input_per_mtok=args.input,
        output_per_mtok=args.output,
        cached_input_per_mtok=args.cached_input,
        cache_write_per_mtok=args.cache_write,
        effective_from=args.effective_from,
        checked_on=args.checked_on or today,
        note=args.note,
    )


async def list_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """모든 모델과 그날의 단가."""
    day = args.on or today
    entries = await service.list_entries(session, day)
    if not entries:
        return ['모델이 없다. add 로 넣는다']
    return [model_line(entry.model, entry.cost, day) for entry in entries]


async def show_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """모델 하나를 자세히."""
    detail = await service.show_model(session, args.slug)
    return detail_lines(detail.model, detail.costs, detail.snapshots, today)


async def add_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """모델을 넣는다. 꺼진 채로 들어간다."""
    model = await service.add_model(session, create_of(args))
    return [f'{model.slug}: 넣었다. 꺼져 있다. 원가를 적고(set-cost), 평가 장면을 통과하면 켠다(enable)']


async def update_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """모델에서 적은 것만 바꾼다."""
    model = await service.update_model(session, args.slug, update_of(args))
    return [f'{model.slug}: 바꿨다']


async def switch_snapshot_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """날짜판을 바꾼다. 모델이 꺼진다."""
    model = await service.switch_snapshot(
        session, args.slug, SnapshotSwitch(api_model_id=args.api_model_id, note=args.note)
    )
    return [
        f'{model.slug}: 날짜판을 {model.api_model_id} 로 바꿨다. 꺼져 있다',
        '평가 장면(말투 검사 포함)을 다시 통과하면 켠다(enable)',
    ]


async def set_cost_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """원가 단가를 덧붙인다."""
    cost = await service.add_cost(session, args.slug, cost_of(args, today))
    return [f'{args.slug}: 단가를 적었다', cost_line(cost)]


async def enable_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """모델을 켠다."""
    model = await service.enable_model(session, args.slug, today)
    return [f'{model.slug}: 켰다']


async def disable_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """모델을 끈다."""
    model = await service.disable_model(session, args.slug)
    return [f'{model.slug}: 껐다']


async def retire_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """은퇴일을 적거나 지운다."""
    model = await service.retire_model(session, args.slug, None if args.cancel else args.on)
    if model.retires_on is None:
        return [f'{model.slug}: 은퇴일을 지웠다']
    return [f'{model.slug}: {model.retires_on}부터 쓰지 않는다']


async def fallback_command(session: AsyncSession, args: argparse.Namespace, today: date) -> list[str]:
    """회사의 대체 모델을 정하거나 지운다."""
    if args.cancel:
        model = await service.clear_fallback(session, args.slug)
        return [f'{model.slug}: 대체 모델에서 뺐다. {model.vendor} 는 standard 중 가장 싼 모델로 대체한다']
    model = await service.set_fallback(session, args.slug, today)
    return [f'{model.slug}: {model.vendor} 의 대체 모델로 정했다']


COMMANDS: dict[str, Command] = {
    'list': list_command,
    'show': show_command,
    'add': add_command,
    'update': update_command,
    'switch-snapshot': switch_snapshot_command,
    'set-cost': set_cost_command,
    'enable': enable_command,
    'disable': disable_command,
    'retire': retire_command,
    'fallback': fallback_command,
}


def add_capability_options(parser: argparse.ArgumentParser, defaults: bool) -> None:
    """모델이 받는 것의 선택지. add 에는 기본값이 있고, update 에는 없다(적은 것만 바꾼다)."""
    parser.add_argument(
        '--reasoning',
        action=argparse.BooleanOptionalAction,
        default=False if defaults else None,
        help='생각의 깊이를 고를 수 있나',
    )
    parser.add_argument(
        '--temperature',
        action=argparse.BooleanOptionalAction,
        default=True if defaults else None,
        help='온도를 받나',
    )
    parser.add_argument(
        '--token-field',
        choices=list(TokenLimitField),
        help='출력 상한의 칸. openai, local 창구만 적는다',
    )
    parser.add_argument(
        '--reasoning-style',
        choices=list(ReasoningStyle),
        help='생각을 켜고 끄는 방식. anthropic, gemini 창구만 적는다. 창구마다 받는 값이 다르다',
    )


def add_model_parsers(commands: argparse._SubParsersAction) -> None:
    """add, update 의 명령줄."""
    add = commands.add_parser('add', help='모델을 넣는다. 꺼진 채로 들어간다')
    add.add_argument('slug', help='이름표. 영어 소문자, 숫자, 붙임표(gpt-6-luna)')
    add.add_argument('--provider', required=True, choices=list(Provider))
    add.add_argument('--api-model-id', required=True, help='API 에 보내는 이름. 날짜가 붙은 이름을 적는다')
    add.add_argument('--name', required=True, help='보이는 이름')
    add.add_argument('--vendor', required=True, help='회사(openai, anthropic, google …)')
    add.add_argument('--grade', required=True, choices=list(Grade))
    add_capability_options(add, defaults=True)

    update = commands.add_parser(
        'update', help='적은 것만 바꾼다. 이름표와 창구는 바꾸지 않는다. 날짜판은 switch-snapshot'
    )
    update.add_argument('slug')
    update.add_argument('--name')
    update.add_argument('--vendor')
    update.add_argument('--grade', choices=list(Grade))
    add_capability_options(update, defaults=False)


def add_snapshot_parser(commands: argparse._SubParsersAction) -> None:
    """switch-snapshot 의 명령줄."""
    switch = commands.add_parser('switch-snapshot', help='날짜판(API 모델 이름)을 바꾼다. 기록이 남고 모델이 꺼진다')
    switch.add_argument('slug')
    switch.add_argument('--api-model-id', required=True, help='새 날짜판. 공식 문서의 날짜 붙은 이름')
    switch.add_argument('--note', help='덧붙일 말(공급자의 공지 …)')


def add_cost_parser(commands: argparse._SubParsersAction) -> None:
    """set-cost 의 명령줄."""
    cost = commands.add_parser('set-cost', help='원가 단가(USD, 백만 토큰당)를 덧붙인다. 앞의 단가는 남는다')
    cost.add_argument('slug')
    cost.add_argument('--input', required=True, type=Decimal)
    cost.add_argument('--output', required=True, type=Decimal)
    cost.add_argument('--cached-input', type=Decimal, help='캐시 읽기. 따로 값을 매기는 공급자만')
    cost.add_argument('--cache-write', type=Decimal, help='캐시 쓰기. 따로 값을 매기는 공급자만')
    cost.add_argument('--from', dest='effective_from', required=True, type=date.fromisoformat, help='이 날부터의 값')
    cost.add_argument('--checked-on', type=date.fromisoformat, help='공식 가격표에서 확인한 날. 적지 않으면 오늘')
    cost.add_argument('--note', help='덧붙일 말(행사가 …)')


def add_switch_parsers(commands: argparse._SubParsersAction) -> None:
    """enable, disable, retire, fallback 의 명령줄."""
    commands.add_parser('enable', help='켠다. 오늘의 원가가 있어야 한다').add_argument('slug')
    commands.add_parser('disable', help='끈다. 지우지 않는다').add_argument('slug')
    retire = commands.add_parser('retire', help='은퇴일을 적는다. 그날부터 쓰지 않는다')
    retire.add_argument('slug')
    when = retire.add_mutually_exclusive_group(required=True)
    when.add_argument('--on', type=date.fromisoformat, help='은퇴일')
    when.add_argument('--cancel', action='store_true', help='은퇴일을 지운다')
    fallback = commands.add_parser(
        'fallback', help='회사의 대체 모델로 정한다. 시나리오의 추천 모델을 쓸 수 없을 때 같은 회사의 이 모델로 바꾼다'
    )
    fallback.add_argument('slug')
    fallback.add_argument('--cancel', action='store_true', help='대체 모델에서 뺀다')


def build_parser() -> argparse.ArgumentParser:
    """명령줄의 모양."""
    parser = argparse.ArgumentParser(description='모델 목록을 다룬다.')
    commands = parser.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('list', help='모든 모델과 오늘의 단가')
    listing.add_argument('--on', type=date.fromisoformat, help='이 날의 단가로 본다')
    commands.add_parser('show', help='모델 하나와 그 단가들').add_argument('slug')
    add_model_parsers(commands)
    add_snapshot_parser(commands)
    add_cost_parser(commands)
    add_switch_parsers(commands)
    return parser


def refusal_lines(error: Exception) -> list[str]:
    """거절된 까닭을 찍을 줄로. 모양이 틀렸으면 틀린 칸마다 한 줄이다."""
    if isinstance(error, ValidationError):
        return [f'{".".join(str(part) for part in item["loc"]) or "입력"}: {item["msg"]}' for item in error.errors()]
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
            code, lines = await execute(session, args, today_utc())
    finally:
        await engine.dispose()
    print('\n'.join(lines), file=sys.stderr if code else sys.stdout)
    return code


def main() -> None:
    """명령줄을 읽고 돌린다."""
    sys.exit(asyncio.run(run(build_parser().parse_args())))


if __name__ == '__main__':
    main()

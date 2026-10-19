# trpg-server/scripts/ci_groups.py

"""
CI 가 게임 서버의 테스트를 관련 있는 것끼리 묶어 여러 작업으로 나눠 돌리게 한다.

    uv run python -m scripts.ci_groups list            묶음의 이름들, 한 줄에 하나
    uv run python -m scripts.ci_groups json            묶음의 이름들, JSON 목록(CI 의 matrix 가 읽는다)
    uv run python -m scripts.ci_groups files rounds    그 묶음의 테스트 파일들(pytest 에 넘긴다)
    uv run python -m scripts.ci_groups summary         묶음마다 파일 수

trpg-server 폴더에서 -m 으로 돌린다. DB 도 설정도 쓰지 않는다. 파일 이름만 본다.
표준 라이브러리만 쓰므로 CI 는 의존성을 설치하기 전에도 python3 로 부를 수 있다.

묶는 법:
  - 묶음마다 파일 이름의 머리(test_ 뒤)를 적는다. 위의 묶음부터 보고 처음 맞는 묶음에 든다.
  - 어느 머리에도 맞지 않는 파일은 마지막 묶음(platform)에 든다. 새 테스트 파일을 만들고 여기를 고치지 않아도
    CI 에서 빠지지 않는다. 다만 관련 있는 묶음에 두려면 머리를 더한다.
  - 한 파일은 한 묶음에만 든다. 두 묶음에 들거나 어느 묶음에도 들지 않는 파일은 없다(tests/test_ci_groups.py).
"""

import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

# 테스트 파일이 있는 곳. trpg-server 폴더에서의 경로다
TESTS_DIR = Path('tests')
# 테스트 파일의 머리. pytest 가 모으는 이름이다
TEST_PREFIX = 'test_'
# 어느 머리에도 맞지 않는 파일이 드는 묶음
CATCH_ALL = 'platform'

# 묶음의 이름과 그 묶음에 드는 파일 이름의 머리(test_ 뒤). 위에서부터 보고 처음 맞는 묶음에 든다.
# 이름은 CI 의 작업 이름에 그대로 나온다
GROUPS: dict[str, tuple[str, ...]] = {
    # 제작자의 자산: 세계관, 룰북, 로어북, 몬스터 모음, 시나리오와 판, 추천 모델, 페르소나, 공개 목록
    'assets': (
        'world',
        'rulebook',
        'lorebooks_api',
        'bestiar',
        'scenario',
        'versions_api',
        'asset_',
        'recommended_model',
        'persona',
        'listings',
        'lobby',
    ),
    # 엔진의 규칙: 판정, 캐릭터 만들기와 시트, 부상과 치료, 죽음, 쉬기
    'engine': (
        'action',
        'check',
        'called_shots',
        'sheet',
        'ruleset',
        'creation',
        'score_roll',
        'point_buy',
        'rolled_abilities',
        'manual_abilities',
        'engine_health',
        'death',
        'character_death',
        'injur',
        'treatment',
        'rest',
    ),
    # 라운드: 열고 닫기, 선언과 판정의 흐름, 시간 제한, 복구, 라운드의 값
    'rounds': (
        'round_',
        'rounds_api',
        'roll_locking',
    ),
    # 모험: 몬스터와 조우, 맵과 이동, 물건(쓰기, 건네기, 줍기, 내려놓기, 훔치기), NPC 의 행동, 퀘스트
    'adventure': (
        'monster',
        'encounters',
        'map_actions',
        'item_actions',
        'place_items',
        'put_down',
        'steal',
        'npc_actions',
        'quest',
        'travel_time',
    ),
    # 모델과 값: 모델 호출과 창구, 모델 목록, 서술의 값과 크레딧 기다림
    'models': (
        'anthropic',
        'gemini',
        'openai_compat',
        'streaming',
        'embedder',
        'call_',
        'retry_budget',
        'ai_log',
        'model_',
        'models_script',
        'try_',
        'price',
        'billing_client',
        'per_head_charges',
        'narration_billing',
        'narration_model_pick',
        'credit_waits',
    ),
    # 서술: 프롬프트, 서술자, 로어와 기억의 검색
    'narration': (
        'narrat',
        'clock_narration',
        'llm_narrator',
        'retrying_narrator',
        'truncated_narration',
        'prompt',
        'preview',
        'naming',
        'lore_',
        'memory',
        'person_history',
        'state_eval',
    ),
    # 테이블: 방, 자리, 캐릭터의 교체, 테이블의 시트·물건·맵·퀘스트·시계
    'tables': (
        'table',
        'clean_tables',
        'replacement',
        'character_mode',
        'npc_sheets',
    ),
    # 실시간: 대화, 귓속말, 기록, 스트림, 신호
    'realtime': (
        'chat_',
        'whisper',
        'event',
        'stream',
        'realtime',
        'signed_signals',
        'shutdown',
        'typing',
    ),
    # 기반과 나머지: 앱, 설정, DB, 인증, 관측, 작업, 알림, 운영자. 어느 머리에도 맞지 않는 파일도 여기다
    CATCH_ALL: (),
}


def group_of(file_name: str) -> str:
    """테스트 파일 하나(test_rounds_api.py)가 드는 묶음."""
    stem = file_name.removeprefix(TEST_PREFIX).removesuffix('.py')
    for group, heads in GROUPS.items():
        if any(stem.startswith(head) for head in heads):
            return group
    return CATCH_ALL


def files_in(group: str, file_names: Iterable[str]) -> list[str]:
    """그 묶음에 드는 파일들. 이름 차례다."""
    return sorted(name for name in file_names if group_of(name) == group)


def list_test_files(tests_dir: Path = TESTS_DIR) -> list[str]:
    """pytest 가 모으는 테스트 파일들의 이름."""
    return sorted(path.name for path in tests_dir.glob(f'{TEST_PREFIX}*.py'))


def run(argv: Sequence[str], file_names: Sequence[str]) -> str:
    """명령줄을 읽어 찍을 글을 만든다. 모르는 명령이나 묶음이면 ValueError 다."""
    match list(argv):
        case ['list']:
            return '\n'.join(GROUPS)
        case ['json']:
            return json.dumps(list(GROUPS))
        case ['files', group] if group in GROUPS:
            return ' '.join(str(TESTS_DIR / name) for name in files_in(group, file_names))
        case ['summary']:
            return '\n'.join(f'{group}: {len(files_in(group, file_names))}' for group in GROUPS)
        case _:
            raise ValueError(f'모르는 명령이다: {" ".join(argv)}. list, json, files <묶음>, summary 중 하나')


def main() -> None:
    """명령줄의 진입점."""
    try:
        print(run(sys.argv[1:], list_test_files()))
    except ValueError as error:
        sys.exit(str(error))


if __name__ == '__main__':
    main()

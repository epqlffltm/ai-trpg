# tools/model_slugs.py

"""
결제 서버에 넣을 판매가 파일(docs/model-prices-*.csv)의 모델 가격 코드가 모델 목록의 파일에 있는 모델을
가리키는지 본다(#499).

    사용: python3 tools/model_slugs.py

모델의 가격 코드는 <머리>.<이름표>.i<입력 단계>.o<출력 단계> 다. 머리는 부르는 서버마다 다르다
(게임 서버 narration, chat 서버 chat, story 서버 story. billing-server/README.md 의 "서버마다의 가격표").
판매가는 결제 서버가, 모델과 원가는 모델 목록의 파일(shared/ai-core/src/ai_core/model_catalog.toml)이 원본이라
둘을 따로 고친다. 이름표 하나가 어긋나면 그 값은 팔리지만 서버가 고를 수 있는 모델에 내주지 않는다(조용히 빠진다).

한쪽만 본다: 판매가가 있으면 모델이 있어야 한다. 판매가가 없는 모델은 된다(혼자 쓰는 시험용, 아직 팔지 않는 모델).
판매가 파일은 이름이 가장 늦은 것(날짜와 판이 붙어 있다) 하나를 본다. 앞의 판은 기록으로 남은 것이다.
아직 부를 수 없어 모델 목록에 넣지 못한 이름표는 까닭과 함께 WAITING 에 적는다. 넣으면 거기서 지운다
(지우지 않으면 테스트가 실패한다).
모델이 아닌 가격 코드(출석 보상 같은)와 단계가 없는 옛 코드(narration.standard)는 보지 않는다.

CI 의 repo-python 이 PR 마다 tools/test_model_slugs.py 로 돌린다. 표준 라이브러리만 쓴다.
"""

import csv
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG = REPO_ROOT / 'shared' / 'ai-core' / 'src' / 'ai_core' / 'model_catalog.toml'
DOCS = REPO_ROOT / 'docs'
PRICE_FILES = 'model-prices-*.csv'

# 판매가는 있지만 아직 모델 목록에 넣지 못한 이름표와 그 까닭
WAITING = {
    'kimi-k3': 'Moonshot(Kimi)의 창구가 아직 없다',
    'kimi-k2-6': 'Moonshot(Kimi)의 창구가 아직 없다',
    'deepseek-flash': 'DeepSeek 은 DeepInfra 로 부른다. 그곳의 Flash 판에서 생각을 끄는 법을 확인한 뒤 이름표를 정한다',
}

# 모델의 가격 코드. 가운데가 이름표다
MODEL_CODE = re.compile(r'^(narration|chat|story)\.(?P<slug>[^.]+)\.i\d+\.o\d+$')


def catalog_slugs(path: Path) -> set[str]:
    """모델 목록의 파일에 있는 이름표들."""
    with path.open('rb') as file:
        return {model['slug'] for model in tomllib.load(file).get('models', [])}


def latest_price_file(docs: Path) -> Path | None:
    """이름이 가장 늦은 판매가 파일. 없으면 None."""
    files = sorted(docs.glob(PRICE_FILES))
    return files[-1] if files else None


def data_rows(path: Path) -> list[list[str]]:
    """판매가 파일의 값 줄들. 머리 줄, 빈 줄, # 로 시작하는 줄은 뺀다."""
    with path.open(encoding='utf-8', newline='') as file:
        rows = [row for row in csv.reader(file) if row and not row[0].startswith('#')]
    return rows[1:]


def priced_slugs(path: Path) -> set[str]:
    """판매가 파일의 모델 가격 코드가 가리키는 이름표들."""
    found = (MODEL_CODE.match(row[0].strip()) for row in data_rows(path))
    return {match['slug'] for match in found if match}


def unknown_slugs(catalog: Path, docs: Path, waiting: frozenset[str] = frozenset()) -> list[str]:
    """판매가는 있는데 모델 목록에 없는 이름표들. 기다리는 것(waiting)은 뺀다. 판매가 파일이 없으면 빈 목록이다."""
    prices = latest_price_file(docs)
    if prices is None:
        return []
    return sorted(priced_slugs(prices) - catalog_slugs(catalog) - waiting)


def main() -> int:
    """어긋난 이름표가 있으면 찍고 1 로 끝낸다."""
    unknown = unknown_slugs(CATALOG, DOCS, frozenset(WAITING))
    for slug in unknown:
        print(f'{slug}: 판매가는 있는데 모델 목록의 파일에 없다', file=sys.stderr)
    return 1 if unknown else 0


if __name__ == '__main__':
    sys.exit(main())

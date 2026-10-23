# trpg-server/app/engine/templates/__init__.py

"""
미리 채워 둔 규칙(템플릿, #615). 원본은 이 폴더의 JSON 파일이다. 템플릿마다 파일 하나다(srd5.json …).

룰북을 만들 때 템플릿 하나를 고른다. 그 값이 룰북에 복사된다(app/assets/rulebooks/service.py).
복사한 뒤에는 룰북의 것이다. 템플릿을 다시 보지 않는다. 게시하면 판에 굳는다.
엔진은 템플릿을 모른다. 규칙(Ruleset)만 받는다.

파일은 앱이 뜰 때 한 번 읽고 Ruleset 의 모양으로 검증한다. 하나라도 틀리면 앱이 뜨지 않는다(테스트가 먼저 잡는다).
  - format 이 이 코드가 아는 판(FORMAT)과 다르면 읽지 않는다. 판정 방식처럼 규칙의 뜻이 바뀌면 판을 올린다(#404)
  - 파일의 이름, key, 규칙의 template 이 같아야 한다
  - 고를 수 있는 템플릿은 Template 에 적은 것이다. Template 과 파일이 하나씩 맞아야 한다
JSON 인 까닭은 규칙에 "없음"(null)인 칸이 많아서다. TOML 에는 null 이 없다. 칸을 빠뜨리면 지금처럼 거절한다.
JSON 에는 주석이 없다. 출처와 본뜬 것은 파일의 notes 와 attribution 에 적는다.

이미 내놓은 템플릿의 값은 고치지 않는다. 고치고 싶으면 새 이름으로 하나 더 낸다.
옛 판을 읽을 때 "그때의 규칙"으로 SRD5 의 값을 쓰기 때문이다(app/assets/scenarios/upgrades.py).
규칙의 모양에 칸이 새로 생기면 템플릿에도 그 칸을 더한다. 있던 값은 그대로 둔다.
그 칸이 없던 때의 룰북과 판에는 같은 값을 채운다(마이그레이션, 판의 올려 읽기).
값이 그대로인지는 tests/test_templates.py 가 해시로 본다.

템플릿의 이름에 상용 룰의 이름을 쓰지 않는다. 본뜬 공개 문서가 있으면 그 출처 표시를 attribution 에 싣는다.
"""

import enum
import json
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.engine.ruleset import Key, Name, Ruleset

# 이 코드가 읽는 템플릿 파일의 판
FORMAT = 1
# 템플릿 파일이 있는 곳
TEMPLATES_DIR = Path(__file__).parent

# 템플릿을 고르는 사람에게 보여 주는 소개
TEMPLATE_SUMMARY_MAX_LENGTH = 200
# 출처 표시 한 줄과, 본뜬 것을 적는 메모 한 줄
TEMPLATE_LINE_MAX_LENGTH = 500
TEMPLATE_MAX_LINES = 30

Summary = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TEMPLATE_SUMMARY_MAX_LENGTH)]
Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TEMPLATE_LINE_MAX_LENGTH)]
Lines = Annotated[tuple[Line, ...], Field(max_length=TEMPLATE_MAX_LINES)]


class Template(enum.StrEnum):
    """고를 수 있는 템플릿. 이름마다 이 폴더에 {이름}.json 이 있다."""

    # d20 판타지. System Reference Document 5.1 을 본떴다
    SRD5 = 'srd5'
    # 공포. 능력치 넷, d20. 부상이 무겁고 빨리 죽는다
    HORROR = 'horror'
    # 가벼운 모험. 능력치 셋, d10. 부상과 죽음의 굴림이 없다
    LIGHT = 'light'


# 룰북을 만들 때 템플릿을 고르지 않으면 쓰는 것
DEFAULT_TEMPLATE = Template.SRD5


class TemplateFile(BaseModel):
    """
    템플릿 파일 하나의 모양.

    rules 가 룰북에 복사되는 규칙이다. 나머지는 고르는 사람에게 보여 주는 것과 출처다.
    attribution 은 출처 표시의 글(바꾸지 않고 싣는다), notes 는 무엇을 본떴고 무엇을 이 프로젝트가 정했는지다.
    """

    model_config = ConfigDict(frozen=True, extra='forbid')

    format: int
    key: Key
    name: Name
    summary: Summary
    attribution: Lines
    notes: Lines
    rules: Ruleset


class TemplateFileError(ValueError):
    """템플릿 파일을 읽을 수 없다. 어느 파일의 무엇이 틀렸는지 적는다."""


def template_path(template: Template) -> Path:
    """템플릿의 원본 파일."""
    return TEMPLATES_DIR / f'{template.value}.json'


def file_problem(template: Template, loaded: TemplateFile) -> str | None:
    """읽은 파일이 그 템플릿의 것이 아니면 까닭을 돌려준다. 판, 이름, 규칙의 template 을 본다."""
    if loaded.format != FORMAT:
        return f'판이 {loaded.format} 이다. 이 코드는 {FORMAT} 만 읽는다'
    if loaded.key != template.value:
        return f'key 가 {loaded.key} 다. 파일의 이름({template.value})과 같아야 한다'
    if loaded.rules.template != template.value:
        return f'규칙의 template 이 {loaded.rules.template} 다. 파일의 이름({template.value})과 같아야 한다'
    return None


def read_template(template: Template) -> TemplateFile:
    """템플릿의 원본 파일을 읽어 모양을 본다. 틀리면 TemplateFileError."""
    path = template_path(template)
    try:
        loaded = TemplateFile.model_validate(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError) as error:
        raise TemplateFileError(f'{path.name}: {error}') from error
    problem = file_problem(template, loaded)
    if problem is not None:
        raise TemplateFileError(f'{path.name}: {problem}')
    return loaded


def read_all() -> dict[Template, TemplateFile]:
    """고를 수 있는 템플릿을 모두 읽는다. Template 에 적은 차례다."""
    return {template: read_template(template) for template in Template}


TEMPLATES: dict[Template, TemplateFile] = read_all()

# 옛 판을 읽을 때 "그때의 규칙"으로 쓰는 값(app/assets/scenarios/upgrades.py)
SRD5 = TEMPLATES[Template.SRD5].rules


def from_template(template: Template) -> Ruleset:
    """템플릿의 규칙을 돌려준다. 규칙은 고칠 수 없는 값이라 그대로 내줘도 된다."""
    return TEMPLATES[template].rules


def all_templates() -> list[TemplateFile]:
    """고를 수 있는 템플릿들. Template 에 적은 차례다."""
    return list(TEMPLATES.values())

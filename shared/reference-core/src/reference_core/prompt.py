# shared/reference-core/src/reference_core/prompt.py

"""
고른 참고 자료를 대화 서버(chat, story)의 프롬프트에 넣는 블록. DB 도 모델도 모른다.

    [참고 자료]
    바깥 자료(...)에서 ... 고른 것이다. ...
    [상식]은 실제 세계의 백과사전에서 온 것이다. ...   ← [상식](위키백과)의 줄이 있을 때만
    - [몬스터] 리치: ...

게임 서버(trpg)는 자기 블록을 쓴다(app/rounds/prompt.py). 결과는 엔진이 정했다는 말이 더 붙는다.
종류의 이름과 [상식]의 규칙은 여기 한 곳에 두고 게임 서버도 가져다 쓴다.
"""

from collections.abc import Sequence

from reference_core.records import ReferenceKind, StoredReference

TITLE = '[참고 자료]'
# 종류 앞에 붙는 이름
KIND_NAMES: dict[str, str] = {ReferenceKind.MONSTER: '몬스터', ReferenceKind.ITEM: '물건', ReferenceKind.TOPIC: '상식'}
# [상식](위키백과)의 줄이 있을 때만 붙이는 말. 실제 세계의 백과사전이라 판타지 장면에 그 세계의 것이 섞이지 않게 한다.
# 받는 도구가 연도와 나라 이름이 든 문장을 빼지만 다 거르지는 못한다
TOPIC_RULE = (
    '[상식]은 실제 세계의 백과사전에서 온 것이다. 사물의 생김새와 쓰임만 참고한다. '
    '실제 세계의 나라, 도시, 인물, 연도는 장면에 쓰지 않는다.'
)
# 대화 서버의 블록 머리말. 바깥 자료라 설정과 맞지 않을 수 있다.
# 글에는 수치가 없지만(reference_core/srd.py), 모델이 원본의 규칙을 떠올려 덧붙이지 않게 적는다
CONVERSATION_NOTE = (
    '바깥 자료(D&D SRD 5.1, 위키백과)에서 지금의 대화와 관련 있을 수 있는 것을 고른 것이다. '
    '생김새, 쓰임, 버릇을 그리는 데만 쓴다. 위의 설정과 다르면 설정을 따르고, 맞지 않으면 쓰지 않는다. '
    '수치와 규칙(피해, 난이도, 횟수)은 쓰지 않는다. 이름은 장면에 맞게 부른다.'
)


def kind_name(kind: str) -> str:
    """종류 앞에 붙는 이름. 모르는 종류면 그대로다."""
    return KIND_NAMES.get(kind, kind)


def reference_line(reference: StoredReference) -> str:
    """한 줄. 앞에 종류를 붙이고, 한국어로 옮긴 이름과 글이 있으면 그것을 쓴다."""
    return f'- [{kind_name(reference.kind)}] {reference.shown_name}: {reference.shown_content}'


def render_references(references: Sequence[StoredReference]) -> str | None:
    """대화 서버의 [참고 자료] 블록. 고른 것이 없으면 None 이다."""
    if not references:
        return None
    rules = [TOPIC_RULE] if any(reference.kind == ReferenceKind.TOPIC for reference in references) else []
    return '\n'.join([TITLE, CONVERSATION_NOTE, *rules, *(reference_line(reference) for reference in references)])

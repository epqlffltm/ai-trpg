# shared/reference-core/src/reference_core/texts.py

"""
참고 자료의 한 줄을 벡터로 바꿀 글로 만든다. DB 도 모델도 모르는 순수한 함수다.

생김새 글(look_ko)이 있으면 이름과 생김새 글이다. 서술자에게 가는 글(생김새 글 + 규칙 요약)과 다르다.
규칙 요약("중형 괴물류, 이동: 걷기 …")이 섞이면 생김새로 부른 장면과 멀어지고, 다른 이름은 고르는 규칙이 따로 본다.
2026-11-27 평가(bge-m3, 장면 70개)에서 맞힘이 64% 에서 79% 로 올랐다. 이름으로 부른 장면은 그대로 100% 였다.
생김새 글이 없으면(위키백과) 로어북 항목과 같은 모양이다. 이름, 다른 이름, 글이 한 줄씩이다.
다른 이름(한국어 이름)이 들어가야 한국어 장면에서도 영어 원본의 줄이 가까워진다.
글은 한국어로 옮긴 것이 있으면 그것이다.
"""

from reference_core.records import StoredReference


def reference_text(reference: StoredReference) -> str:
    """줄을 벡터로 바꿀 글. 생김새 글이 있으면 이름과 그것이다. 없으면 이름, 다른 이름, 글(비어 있으면 뺀다)이다."""
    if reference.look_ko:
        return f'{reference.name}\n{reference.look_ko}'
    lines = [reference.name]
    if reference.aliases:
        lines.append(f'다른 이름: {", ".join(reference.aliases)}')
    if reference.shown_content:
        lines.append(reference.shown_content)
    return '\n'.join(lines)

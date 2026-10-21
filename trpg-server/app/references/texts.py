# trpg-server/app/references/texts.py

"""
참고 자료의 한 줄을 벡터로 바꿀 글로 만든다. DB 도 모델도 모르는 순수한 함수다.

로어북 항목과 같은 모양이다(app/lore/texts.py). 이름, 다른 이름, 글이 한 줄씩이다.
다른 이름(한국어 이름)이 들어가야 한국어 장면에서도 영어 원본의 줄이 가까워진다.
글은 한국어로 옮긴 것이 있으면 그것이다. 장면이 한국어라 한국어 글과 가깝다. 서술자에게 가는 글과도 같다.
"""

from app.references.records import StoredReference


def reference_text(reference: StoredReference) -> str:
    """줄을 벡터로 바꿀 글. 다른 이름이나 글이 없으면 그 줄을 뺀다."""
    lines = [reference.name]
    if reference.aliases:
        lines.append(f'다른 이름: {", ".join(reference.aliases)}')
    if reference.shown_content:
        lines.append(reference.shown_content)
    return '\n'.join(lines)

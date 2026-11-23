# shared/reference-core/src/reference_core/attributions.py

"""
자료마다의 출처 표시. 화면이 찾은 줄과 함께 보인다. 원본을 바꾼 것(빼고, 줄이고, 옮김)도 함께 적는다
(SRD 5.1 은 CC BY 4.0, 위키백과는 CC BY-SA 4.0).
"""

from collections.abc import Sequence

from reference_core.records import ReferenceSource, StoredReference
from reference_core.srd import SRD51_ATTRIBUTION, SRD51_CHANGES, SRD51_TRANSLATED
from reference_core.wiki import WIKIPEDIA_ATTRIBUTION, WIKIPEDIA_CHANGES, WIKIPEDIA_TRANSLATED

ATTRIBUTIONS: dict[str, str] = {
    ReferenceSource.SRD51: f'{SRD51_ATTRIBUTION} {SRD51_CHANGES}{SRD51_TRANSLATED}',
    ReferenceSource.WIKIPEDIA: f'{WIKIPEDIA_ATTRIBUTION} {WIKIPEDIA_CHANGES}{WIKIPEDIA_TRANSLATED}',
}


def attributions_of(references: Sequence[StoredReference]) -> list[str]:
    """줄들이 나온 자료의 출처 표시. 자료마다 한 번, 처음 나온 차례다."""
    sources = dict.fromkeys(reference.source for reference in references)
    return [ATTRIBUTIONS[source] for source in sources if source in ATTRIBUTIONS]

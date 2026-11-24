# shared/reference-core/tests/test_attributions.py

"""
출처 표시(reference_core/attributions.py)와 패키지에 실린 데이터 파일(reference_core/data.py)을 검증한다.
"""

import uuid

from reference_core.attributions import ATTRIBUTIONS, attributions_of
from reference_core.data import DATA_FILES, SRD51_FILE, SRD51_TRANSLATION_FILE, WIKIPEDIA_FILE
from reference_core.records import ReferenceSource, StoredReference, read_document
from reference_core.wiki import WIKIPEDIA_ATTRIBUTION


def stored(source: str) -> StoredReference:
    return StoredReference(id=uuid.uuid4(), key='k', name='n', source=source)


def test_every_source_has_an_attribution():
    assert set(ATTRIBUTIONS) == set(ReferenceSource)
    assert WIKIPEDIA_ATTRIBUTION in ATTRIBUTIONS[ReferenceSource.WIKIPEDIA]
    assert 'ShareAlike' not in ATTRIBUTIONS[ReferenceSource.SRD51]


def test_attributions_come_once_per_source_in_order():
    lines = [stored('wikipedia'), stored('srd51'), stored('wikipedia'), stored('unknown')]

    assert attributions_of(lines) == [ATTRIBUTIONS['wikipedia'], ATTRIBUTIONS['srd51']]
    assert attributions_of([]) == []


def test_the_shipped_files_are_in_the_package():
    assert DATA_FILES == (SRD51_FILE, WIKIPEDIA_FILE)
    assert SRD51_TRANSLATION_FILE.exists()
    assert read_document(SRD51_FILE).source == ReferenceSource.SRD51
    assert read_document(WIKIPEDIA_FILE).source == ReferenceSource.WIKIPEDIA

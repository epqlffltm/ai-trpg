# shared/reference-core/src/reference_core/srd_build.py

"""
SRD 5.1 의 원본 폴더(JSON)를 읽어 데이터 파일을 쓴다. 개발자의 명령(trpg-server 의 scripts/build_srd.py)이 부른다.

원본은 5e-bits/5e-database 의 src/2014/en 이다. 옮기는 규칙은 reference_core/srd.py 다.
한국어 번역(reference_core/data/srd51.ko.json)이 있으면 붙인다(reference_core/translations.py).
번역에 자료에 없는 key 가 있으면 멈춘다(원본이 바뀌어 빠진 줄이거나 오타다).
DB 와 설정은 쓰지 않는다.
"""

import json
from pathlib import Path
from typing import Any

from reference_core.records import write_document
from reference_core.srd import srd_document, srd_records
from reference_core.translations import apply_translations, read_translations, unknown_keys

# 원본 폴더 안의 파일 이름
MONSTERS_FILE = '5e-SRD-Monsters.json'
EQUIPMENT_FILE = '5e-SRD-Equipment.json'
MAGIC_ITEMS_FILE = '5e-SRD-Magic-Items.json'


class UnknownTranslation(Exception):
    """번역에 자료에 없는 key 가 있다."""


def read_json(folder: Path, name: str) -> list[dict[str, Any]]:
    """원본 폴더의 JSON 파일 하나."""
    return json.loads((folder / name).read_text(encoding='utf-8'))


def build(folder: Path, revision: str, output: Path, translation: Path | None = None) -> int:
    """
    원본을 읽어 데이터 파일을 쓴다. 번역 파일이 있으면 붙인다. 줄의 수를 돌려준다.

    번역에 자료에 없는 key 가 있으면 UnknownTranslation 이다. 쓰지 않는다.
    """
    records = srd_records(
        read_json(folder, MONSTERS_FILE), read_json(folder, EQUIPMENT_FILE), read_json(folder, MAGIC_ITEMS_FILE)
    )
    if translation is not None and translation.exists():
        translations = read_translations(translation)
        unknown = unknown_keys(records, translations)
        if unknown:
            raise UnknownTranslation(', '.join(unknown[:5]))
        records = apply_translations(records, translations)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_document(srd_document(records, revision), output)
    return len(records)

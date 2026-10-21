# trpg-server/scripts/build_srd.py

"""
SRD 5.1 의 원본(JSON)으로 참고 자료의 데이터 파일(data/references/srd51.json)을 만든다. 개발자가 쓴다.

원본은 5e-bits/5e-database 의 src/2014/en 이다. 저장소를 받아 그 폴더를 넘긴다. 원본의 커밋도 적는다(파일에 남는다).
만든 파일은 저장소에 넣는다. 운영 서버는 원본을 받지 않고 이 파일을 넣는다(scripts/references.py load).
옮기는 규칙은 app/references/srd.py 에 있다.

    git clone --depth 1 https://github.com/5e-bits/5e-database.git <폴더>
    uv run python -m scripts.build_srd <폴더>/src/2014/en --revision <원본의 커밋>

trpg-server 폴더에서 -m 으로 돌린다. DB 와 설정은 쓰지 않는다.
"""

import argparse
import json
from pathlib import Path
from typing import Any

from app.references.records import write_document
from app.references.srd import srd_document, srd_records

# 원본 폴더 안의 파일 이름
MONSTERS_FILE = '5e-SRD-Monsters.json'
EQUIPMENT_FILE = '5e-SRD-Equipment.json'
MAGIC_ITEMS_FILE = '5e-SRD-Magic-Items.json'
# 만든 파일을 두는 곳(trpg-server 폴더에서)
DEFAULT_OUTPUT = Path('data/references/srd51.json')


def build_parser() -> argparse.ArgumentParser:
    """명령줄의 모양."""
    parser = argparse.ArgumentParser(description='SRD 5.1 의 원본으로 참고 자료의 데이터 파일을 만든다.')
    parser.add_argument('folder', type=Path, help='원본 폴더(5e-database 의 src/2014/en)')
    parser.add_argument('--revision', required=True, help='원본 저장소의 커밋')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT, help=f'만들 파일. 기본 {DEFAULT_OUTPUT}')
    return parser


def read_json(folder: Path, name: str) -> list[dict[str, Any]]:
    """원본 폴더의 JSON 파일 하나."""
    return json.loads((folder / name).read_text(encoding='utf-8'))


def build(folder: Path, revision: str, output: Path) -> int:
    """원본을 읽어 데이터 파일을 쓴다. 줄의 수를 돌려준다."""
    records = srd_records(
        read_json(folder, MONSTERS_FILE), read_json(folder, EQUIPMENT_FILE), read_json(folder, MAGIC_ITEMS_FILE)
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    write_document(srd_document(records, revision), output)
    return len(records)


def main() -> None:
    """명령줄을 읽고 돌린다."""
    args = build_parser().parse_args()
    count = build(args.folder, args.revision, args.output)
    print(f'{args.output}: {count}줄')


if __name__ == '__main__':
    main()

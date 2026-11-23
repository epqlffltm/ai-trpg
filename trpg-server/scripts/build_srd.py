# trpg-server/scripts/build_srd.py

"""
SRD 5.1 의 원본(JSON)으로 참고 자료의 데이터 파일(reference_core/data/srd51.json)을 만든다. 개발자가 쓴다.

원본은 5e-bits/5e-database 의 src/2014/en 이다. 저장소를 받아 그 폴더를 넘긴다. 원본의 커밋도 적는다(파일에 남는다).
한국어 번역(reference_core/data/srd51.ko.json)이 있으면 붙인다.
만든 파일은 저장소에 넣는다(공용 패키지 shared/reference-core 에 실린다). 운영 서버는 원본을 받지 않고 이 파일을 넣는다
(scripts/references.py load). 읽고 옮기는 것은 reference_core/srd_build.py 와 reference_core/srd.py 다.

    git clone --depth 1 https://github.com/5e-bits/5e-database.git <폴더>
    uv run python -m scripts.build_srd <폴더>/src/2014/en --revision <원본의 커밋>

trpg-server 폴더에서 -m 으로 돌린다. 기본으로 만드는 곳은 저장소 안의 공용 패키지 폴더다(editable 로 깐 것).
DB 와 설정은 쓰지 않는다.
"""

import argparse
from pathlib import Path

from reference_core.data import SRD51_FILE, SRD51_TRANSLATION_FILE
from reference_core.srd_build import build


def build_parser() -> argparse.ArgumentParser:
    """명령줄의 모양."""
    parser = argparse.ArgumentParser(description='SRD 5.1 의 원본으로 참고 자료의 데이터 파일을 만든다.')
    parser.add_argument('folder', type=Path, help='원본 폴더(5e-database 의 src/2014/en)')
    parser.add_argument('--revision', required=True, help='원본 저장소의 커밋')
    parser.add_argument('--output', type=Path, default=SRD51_FILE, help=f'만들 파일. 기본 {SRD51_FILE}')
    parser.add_argument(
        '--translation',
        type=Path,
        default=SRD51_TRANSLATION_FILE,
        help=f'한국어 번역. 파일이 없으면 붙이지 않는다. 기본 {SRD51_TRANSLATION_FILE}',
    )
    return parser


def main() -> None:
    """명령줄을 읽고 돌린다."""
    args = build_parser().parse_args()
    count = build(args.folder, args.revision, args.output, args.translation)
    print(f'{args.output}: {count}줄')


if __name__ == '__main__':
    main()

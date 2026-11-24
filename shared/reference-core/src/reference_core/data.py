# shared/reference-core/src/reference_core/data.py

"""
패키지에 함께 싣는 데이터 파일(reference_core/data/). 서버의 이미지에 설치된 패키지와 함께 들어간다.

  - srd51.json: SRD 5.1 의 몬스터, 장비, 마법 물건(trpg-server 의 scripts/build_srd.py 가 만든다)
  - srd51.ko.json: 그 줄들의 한국어 이름과 글(번역 파일, reference_core/translations.py)
  - wikipedia.json: 고른 위키백과 문서의 도입부(trpg-server 의 scripts/build_wiki.py 가 만든다, CC BY-SA 4.0)
  - wikipedia.ko.json: 영어판으로 받은 줄의 한국어 이름과 글(번역 파일, 만들 때 붙인다)
  - wikipedia-titles.txt: 받을 제목 목록(reference_core/wiki_titles.py)
  - wikipedia-places.txt: 거를 실제 세계의 나라와 도시의 이름(reference_core/wiki.py)
넣기(서버의 scripts/references.py load)는 파일을 주지 않으면 DATA_FILES 를 모두 넣는다.
번역 파일은 데이터 파일을 만들 때 붙이는 것이라 넣지 않는다(이미 데이터 파일에 들어 있다).
"""

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / 'data'
SRD51_FILE = DATA_DIR / 'srd51.json'
SRD51_TRANSLATION_FILE = DATA_DIR / 'srd51.ko.json'
WIKIPEDIA_FILE = DATA_DIR / 'wikipedia.json'
WIKIPEDIA_TRANSLATION_FILE = DATA_DIR / 'wikipedia.ko.json'
WIKIPEDIA_TITLES_FILE = DATA_DIR / 'wikipedia-titles.txt'
WIKIPEDIA_PLACES_FILE = DATA_DIR / 'wikipedia-places.txt'
# 넣기가 기본으로 넣는 데이터 파일들. 자료마다 하나다. 아직 만들지 않은 파일은 뺀다(위키백과는 개발자가 받아 만든다)
DATA_FILES: tuple[Path, ...] = tuple(path for path in (SRD51_FILE, WIKIPEDIA_FILE) if path.exists())

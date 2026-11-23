# shared/reference-core/src/reference_core/__init__.py

"""
참고 자료를 다루는 공용 코드(docs/architecture/shared-code.md 의 "참고 자료").

미리 넣어 둔 바깥 자료(SRD 5.1, 위키백과)를 서술과 대화의 참고로 쓴다. 게임 중에 웹을 찾지 않는다.
trpg 가 만들었고 chat, story 도 같은 규칙으로 쓰려고 모았다.
  - records: 자료의 한 줄과 데이터 파일의 모양, 복사할 수 있는 자료
  - srd, wiki, translations: 원본에서 줄을 만드는 규칙과 출처, 한국어 번역 파일
  - attributions: 자료마다의 출처 표시
  - data: 패키지에 함께 싣는 데이터 파일
  - tables: 서버의 표 둘(ORM 클래스)을 묶어 넘기는 꾸러미
  - repository: 표를 읽고 쓰는 SQL
  - loading: 데이터 파일을 표에 맞추기(넣기)
  - indexing: 벡터 만들기(색인)
  - selection: 장면에 넣을 줄을 고르는 순수한 규칙
  - search: 찾는 글 하나에 맞는 줄을 DB 에서 고르기

표(ORM 클래스와 마이그레이션)는 서버에 있다. 받는 자료와 종류의 제약, 스키마가 서버의 것이라서다.
켰는지(테이블, 대화, 세션), 남은 자리가 얼마인지, 고른 것을 프롬프트에 어떻게 넣는지도 서버가 정한다.
서버의 모듈(app.*)과 server_core 를 가져오지 않는다(tests/test_boundary.py).
"""

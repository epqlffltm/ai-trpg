# shared/catalog-core/src/catalog_core/__init__.py

"""
모델 목록의 표를 다루는 공용 코드(docs/architecture/shared-code.md 의 "모델 목록의 표").

chat, story, trpg 세 서버가 모델 목록의 원본 파일(ai_core/model_catalog.toml)을 제 표에 들여오고 읽는다.
그 규칙이 같아 세 벌로 있던 것을 모았다(#1266).
  - tables: 서버의 표 셋(ORM 클래스)을 묶어 넘기는 꾸러미
  - errors: 모델 목록의 일이 거절되는 까닭
  - repository: 표를 읽고 적는 SQL
  - lookup: 말 한 번에 모델 하나를 찾는 것(ai_core 의 ModelLookup 을 DB 로 채운다)
  - sync: 원본 파일을 표에 들여오기

표(ORM 클래스와 마이그레이션)는 서버에 있다.
Base 와 스키마, 서버만의 스위치(성인 등급, 회사의 대체 모델)가 서버마다 달라서다.
서버는 표를 꾸러미(CatalogTables)로 넘기고, 서버만의 일은 정해 둔 자리(sync 의 on_vendor_change)로만 더한다.
서버의 모듈(app.*)과 server_core 를 가져오지 않는다(tests/test_boundary.py).
"""

# asset-server/app/hearts/__init__.py

"""
캐릭터와 세계관의 관심(하트, #989). 한 사람이 작품 하나에 한 번 둔다.

  - kinds.py: 작품의 종류마다 쓰는 표와 조건(캐릭터, 세계관)
  - repository.py: 두고 거두기, 내 관심 작품. 작품마다의 관심 수(heart_count)를 같은 트랜잭션에서 고친다
  - service.py: 둘 수 있는지(볼 수 있는 작품인지) 보는 규칙
주소는 공개 목록의 라우터(app/characters/listings.py, app/worlds/listings.py)에 있다.
시나리오의 관심은 trpg-server 가 가진다.
"""

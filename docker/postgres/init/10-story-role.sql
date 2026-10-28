-- docker/postgres/init/10-story-role.sql
-- story 서버 전용 DB 계정과 스키마를 만든다.
--
-- 실행 시점: 데이터 볼륨이 비어 있는 첫 기동 때 한 번만 실행된다.
--           이미 데이터가 있는 볼륨에서는 직접 실행해야 한다(story-server/README.md 참고).
-- 실행 주체: POSTGRES_USER (슈퍼유저)

-- 컨테이너 환경 변수에서 비밀번호를 읽어 psql 변수에 담는다
\getenv story_password STORY_DB_PASSWORD

-- CREATEDB 를 주지 않는다. 테스트용 DB 를 새로 만들지 않고, 같은 DB 의 다른 스키마를 쓴다
CREATE ROLE story LOGIN PASSWORD :'story_password';

-- 개발용 스키마. story 서버의 테이블(가져온 세계관, 세션, 메시지, 메시지마다의 상태, 엔딩의 기록)이 여기에 놓인다.
-- 다른 서버의 계정에는 이 스키마의 권한을 주지 않는다. 다른 서버는 story 서버의 API 로만 묻는다.
-- chat 의 대화 표와 모양이 같아도 chat 스키마를 쓰지 않는다(docs/architecture/chat-server.md 의 "story-server 와 나눈 선")
CREATE SCHEMA story AUTHORIZATION story;

-- 테스트용 스키마. 테스트가 개발용 데이터를 건드리지 않게 따로 둔다
CREATE SCHEMA story_test AUTHORIZATION story;

-- pgvector(03-extensions.sql 의 extensions 스키마)를 쓴다. 세계관의 로어북 항목의 벡터를 저장하고 가까운 것을 찾는다.
-- 읽기(USAGE)만 준다. story 서버는 search_path 에 이 스키마를 더한다(story-server/app/core/database.py)
GRANT USAGE ON SCHEMA extensions TO story;

# docker/backup-offsite/Dockerfile
# 바깥 백업(staging, docker-compose.staging.yml 의 backup-offsite)의 이미지.
#
# DB 와 같은 이미지(pgvector)에서 시작한다. 복원을 확인할 때 쓰는 pg_restore 와 psql 이 DB 서버와 같은 판이다.
# 거기에 암호화(age)와 S3 에 올리고 받는 도구(aws CLI)만 더한다. 스크립트는 offsite.sh 하나다.
# DB 서버(postgres)를 띄우지 않는다. 엔트리포인트를 스크립트로 바꾼다.

FROM pgvector/pgvector:pg17

RUN apt-get update \
    && apt-get install -y --no-install-recommends age awscli ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY offsite.sh /usr/local/bin/offsite.sh

ENTRYPOINT ["sh", "/usr/local/bin/offsite.sh"]
CMD ["loop"]

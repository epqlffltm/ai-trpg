# billing-server/Dockerfile
# 결제 서버의 이미지. 저장소 루트의 docker-compose.yml 이 app 프로필로 띄운다.
#
# 단계 둘로 나눈다.
#   build   : 실행 파일 셋(서버, 마이그레이션, 정리 작업)을 만든다
#   runtime : 실행 파일만 담는다. root 가 아닌 사용자로 돈다
#
# 실행 파일은 C 라이브러리에 기대지 않게 만든다(CGO_ENABLED=0). 그래서 작은 alpine 에서 그대로 돈다.
# alpine 에는 compose 의 상태 확인이 쓰는 wget 이 들어 있다.
# 비밀(.env)은 넣지 않는다(.dockerignore). 컨테이너를 띄울 때 compose 가 넘긴다.
# 마이그레이션은 이 이미지로 따로 한 번 돈다(compose 의 billing-migrate). 마이그레이션 파일은 실행 파일 안에 들어 있다.

FROM golang:1.27-alpine3.24 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download
COPY . .
# 빌드한 PC 의 경로를 실행 파일에 남기지 않는다(-trimpath). 디버그 정보를 뺀다(-s -w)
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/ \
        ./cmd/server ./cmd/migrate ./cmd/sweeper

FROM alpine:3.24 AS runtime
# root 가 아닌 사용자. 번호를 고정한다
RUN adduser -D -H -u 10001 -s /sbin/nologin app
WORKDIR /app
COPY --from=build /out/ /app/
# 번호로 적는다. 이름은 바깥(쿠버네티스 등)에서 root 가 아닌지 확인할 수 없다
USER 10001
EXPOSE 8003
CMD ["/app/server"]

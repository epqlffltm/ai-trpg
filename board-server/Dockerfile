# board-server/Dockerfile
# 게시판 서버의 이미지. 저장소 루트의 docker-compose.yml 이 app 프로필로 띄운다.
#
# 단계 둘로 나눈다.
#   build   : 모든 패키지를 깔고 타입스크립트를 빌드한 뒤, 개발용 패키지를 걷어 낸다
#   runtime : 빌드한 것과 실행에 필요한 패키지만 담는다. root 가 아닌 사용자(node)로 돈다
#
# 비밀(.env)은 넣지 않는다(.dockerignore). 컨테이너를 띄울 때 compose 가 넘긴다.
# 마이그레이션은 이 이미지로 따로 한 번 돈다(compose 의 board-migrate). 서버가 뜰 때 돌리지 않는다.

FROM node:24-trixie-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
# 잠금 파일 그대로 깐다. 어긋나면 실패한다
RUN --mount=type=cache,target=/root/.npm \
    npm ci
COPY . .
RUN npm run build \
    && npm prune --omit=dev

FROM node:24-trixie-slim AS runtime
ENV NODE_ENV=production
WORKDIR /app
# 파일의 주인은 root 로 둔다. 서버는 읽기만 한다. 서버가 뚫려도 제 코드를 고쳐 쓰지 못한다
COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
# 노드 이미지에 들어 있는 root 가 아닌 사용자(node)의 번호. 번호로 적는다.
# 이름은 바깥(쿠버네티스 등)에서 root 가 아닌지 확인할 수 없다
USER 1000
EXPOSE 8002
CMD ["node", "dist/main.js"]

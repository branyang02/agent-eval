FROM oven/bun:1 AS viewer-build

WORKDIR /viewer

COPY viewer/package.json viewer/bun.lock viewer/tsconfig.json ./
COPY viewer/scripts ./scripts
COPY viewer/src ./src

RUN bun install --frozen-lockfile
RUN bun run typecheck
RUN bun run build

FROM python:3.12-slim

WORKDIR /conversation-server

RUN pip install --no-cache-dir tyro==1.0.13

COPY server.py /conversation-server/server.py
COPY --from=viewer-build /viewer/dist /conversation-server/viewer/dist

EXPOSE 8000

CMD ["python3", "/conversation-server/server.py"]

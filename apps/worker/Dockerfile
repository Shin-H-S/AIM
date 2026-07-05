FROM node:22.21-bookworm-slim AS node-runtime

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    CHROME_PATH=/usr/local/bin/chromium \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN ln -sf ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack \
    && ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/package.json
RUN corepack pnpm install --frozen-lockfile --prod

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/api/src ./apps/api/src
COPY apps/worker/src ./apps/worker/src
COPY migrations ./migrations
RUN uv sync --frozen --no-dev \
    && playwright install --with-deps chromium \
    && chromium_path="$(find /ms-playwright -type f \( -path '*/chrome-linux/chrome' -o -path '*/chrome-linux64/chrome' \) | head -n 1)" \
    && test -n "${chromium_path}" \
    && ln -s "${chromium_path}" /usr/local/bin/chromium

RUN groupadd --system aim \
    && useradd --system --gid aim --create-home aim \
    && mkdir -p /data/aim/artifacts \
    && chown -R aim:aim /app /data/aim /ms-playwright

USER aim

CMD ["celery", "-A", "aim_worker.celery_app.celery_app", "worker", "--loglevel=INFO", "--concurrency=1"]

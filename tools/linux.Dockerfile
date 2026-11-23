FROM caddy:2.11.9@sha256:4851e54a46b206517c574821bb5cc67f170d2156041e9fbc4c9193b45e84a75b AS caddy
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS build
RUN apt-get update && apt-get install -y --no-install-recommends binutils tk && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY . .
COPY --from=caddy /usr/bin/caddy /src/route/bin/caddy
RUN pip install --no-cache-dir . 'pyinstaller>=6.12,<7'
RUN python -m unittest tests.test_relay tests.test_images tests.test_setup.SetupTest.test_connection_challenge tests.test_setup.SetupTest.test_lifecycle tests.test_setup.SetupTest.test_first_run_key_and_default_selection
RUN python tools/package.py && dpkg -i dist/*.deb && route-for-codex status
FROM scratch
COPY --from=build /src/dist/ /

FROM python:3.12-slim
RUN useradd -m -u 10001 runner && mkdir /work && chown runner /work
USER runner
WORKDIR /work

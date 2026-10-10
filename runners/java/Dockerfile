FROM eclipse-temurin:21-jdk
RUN useradd -m -u 10001 runner && mkdir /work && chown runner /work
USER runner
WORKDIR /work

# C and C++ (gcc / g++ 13)
FROM gcc:13
RUN useradd -m -u 10001 runner && mkdir /work && chown runner /work
USER runner
WORKDIR /work

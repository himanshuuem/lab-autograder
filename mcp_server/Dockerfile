FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY classroom_mcp ./classroom_mcp
RUN useradd -m -u 10002 mcp
USER mcp
EXPOSE 8200
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8200/health')"
CMD ["python", "-m", "classroom_mcp.server"]

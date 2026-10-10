FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY sandbox ./sandbox
EXPOSE 8100
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8100/health')"
CMD ["uvicorn", "sandbox.main:app", "--host", "0.0.0.0", "--port", "8100"]

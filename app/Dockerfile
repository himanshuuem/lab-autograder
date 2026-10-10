# build context: repository root (needs packages/docextract)
FROM python:3.12-slim
# tesseract: scanned pages and screenshots; LibreOffice: Word/ODT/RTF submissions.
# Liberation/Carlito fonts match Courier New/Arial/Calibri metrics, so converted code keeps its layout.
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-eng \
      libreoffice-writer-nogui fonts-liberation fonts-crosextra-carlito fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# PowerPoint and Excel submissions (own layer, after the slow ones, so they stay cached)
RUN apt-get update && apt-get install -y --no-install-recommends \
      libreoffice-impress-nogui libreoffice-calc-nogui \
    && rm -rf /var/lib/apt/lists/*
COPY packages/docextract /tmp/docextract
RUN pip install --no-cache-dir /tmp/docextract && rm -rf /tmp/docextract
COPY app/autograder ./autograder
COPY app/static ./static
RUN useradd -m -u 10003 app && mkdir -p /data && chown app /data
USER app
ENV DATA_DIR=/data
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["uvicorn", "autograder.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

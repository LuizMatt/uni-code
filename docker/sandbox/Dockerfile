FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir \
    "pytest>=8.3.0" \
    "pytest-json-report>=1.5.0"

COPY sandbox_entry.py /usr/local/bin/sandbox_entry.py
RUN chmod 0555 /usr/local/bin/sandbox_entry.py

WORKDIR /tmp
USER 65534:65534

ENTRYPOINT ["python", "-I", "/usr/local/bin/sandbox_entry.py"]

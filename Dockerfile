FROM python:3.12-slim

WORKDIR /app

# Semgrep needs git for some rulesets and a C compiler for optional deps.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Verify semgrep is importable and can run a minimal scan.
RUN python -c "import semgrep; print('semgrep import ok')" && \
    semgrep --version

COPY app/ ./app/
COPY scripts/ ./scripts/
COPY tests/samples/ ./tests/samples/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

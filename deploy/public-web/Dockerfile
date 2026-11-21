FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JEJU_ROOT=/app \
    NUMBA_CACHE_DIR=/tmp/hanjang-jeju-numba \
    NUMBA_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY .python-version ./
COPY app.py ./
COPY src/ src/
COPY data/reference/ data/reference/
COPY public/ public/
COPY web-release-manifest.json ./
EXPOSE 10000
CMD ["sh", "-c", "exec python -m uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips '*'"]

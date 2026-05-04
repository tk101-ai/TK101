FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/srv

WORKDIR /srv

COPY pyproject.toml ./

# PyTorch는 CPU-only 휠로 먼저 설치. 기본 PyPI 휠은 nvidia-cu13 등 CUDA 의존성을
# ~5GB 끌어와서 디스크/이미지가 폭증한다. 운영은 CPU 추론만 하므로 CUDA 불필요.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

# 나머지 의존성 (sentence-transformers 등). torch는 이미 설치돼 있어 재해석 X.
RUN pip install --no-cache-dir $(python -c "\
import tomllib, pathlib; \
d = tomllib.loads(pathlib.Path('pyproject.toml').read_text()); \
print(' '.join(d['project']['dependencies']))")

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

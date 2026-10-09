FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

# OCR system dependencies. Keep the image lean and clear apt metadata.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY . /code
RUN mkdir -p \
      /code/app/uploads/claims \
      /code/app/uploads/medical_documents \
      /code/app/uploads/policies \
      /code/app/uploads/policy_repository \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /code

# Run as a non-root user.
USER appuser

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-${port:-8000}}"]

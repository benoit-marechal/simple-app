FROM python:3.12-slim

RUN apt-get update && apt-get install -y --only-upgrade zlib1g && apt-get clean
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip==26.3
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY messages.py .
COPY object_storage.py .
COPY session_files.py .
COPY prepare_secrets.py .
COPY templates/ templates/

RUN mkdir /data /sessions /run/s3 && chown 1000:1000 /data /sessions
USER 1000:1000
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--access-logfile", "-", "--error-logfile", "-", "app:app"]

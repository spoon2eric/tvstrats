FROM python:3.10-alpine

WORKDIR /usr/src/app

COPY requirements.txt .

RUN apk --no-cache add sqlite && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5001

CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "1", "--threads", "4", "--timeout", "120", "main:app"]

FROM python:3.7-alpine

LABEL Name=crawler-multi Version=0.0.1

WORKDIR /app
ADD . /app

RUN apk add --no-cache --virtual .build-deps gcc libc-dev libxslt-dev && \
    apk add --no-cache libxslt && \
    pip install --no-cache-dir -r requirements.txt && \
    apk del .build-deps


CMD ["python3", "-m", "src.run_multi"]

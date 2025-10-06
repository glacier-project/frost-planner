FROM python:3.13.2-alpine3.21

RUN mkdir /app
WORKDIR /app

RUN pip install --upgrade pip && apk add gzip
COPY requirements.txt requirements.txt
RUN apk add --update --no-cache --virtual .tmp-build-deps gcc libc-dev zlib-dev && pip install -r requirements.txt && apk del .tmp-build-deps
COPY resources/ resources
COPY frost_planner/ frost_planner
COPY examples/ examples

# Generate *.pyc files
RUN python -m compileall -o 2 -f -j 0 /app/frost_planner/

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8
ENV PYTHONPATH="${PYTHONPATH}:/app"

CMD ["python", "examples/simple_job_shop.py.py"]
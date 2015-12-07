FROM alpine:3.2

RUN apk add --update curl python3

RUN curl -fLO https://bootstrap.pypa.io/get-pip.py && python3 get-pip.py

RUN ln -s python3 /usr/bin/python

RUN pip install riemann-client

COPY docker.py events.py riemann.py /src/

WORKDIR /src

CMD ["python3", "./events.py"]

VOLUME /srv/events

FROM python:3-onbuild

COPY events.py /usr/src/app/
COPY docker.py /usr/src/app/
COPY riemann.py /usr/src/app/
COPY debug.py /usr/src/app/

CMD ["python", "-u", "./events.py"]

FROM python:3.8.0-slim

RUN pip3 install discord

COPY ./src/ /usr/local/bin/

COPY ./custom-default.conf /etc/nginx/conf.d/default.conf

CMD ["python3 predictions.py"]

FROM python:3.8-slim

COPY ./requirements.txt /
RUN pip install -r /requirements.txt
COPY ./src/ /usr/local/bin/

ENTRYPOINT [ "python3", "/usr/local/bin/predictions-bot.py" ]

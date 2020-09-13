FROM python:3.8-slim

COPY ./requirements.txt /

RUN apt-get update && apt-get install -y build-essential

RUN pip install -r /requirements.txt

COPY ./src/ /usr/local/bin/

ENTRYPOINT [ "python3", "/usr/local/bin/prediction-bot.py" ]

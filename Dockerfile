from python:3.10-slim-buster

ARG BUILD_DATE
ARG VCS_REF

# Set labels (see https://microbadger.com/labels)
LABEL org.label-schema.build-date=$BUILD_DATE \
      org.label-schema.vcs-ref=$VCS_REF \
      org.label-schema.name="rflink2mqtt" \
      org.label-schema.vendor="Mickael HUBERT <mickael@winlux.fr>"


RUN mkdir -p /usr/src/app
WORKDIR /usr/src/app

RUN pip3 install --upgrade pip

COPY requirements.txt /usr/src/app/
RUN pip3 install --no-cache-dir -r requirements.txt

COPY rflink2mqtt.py /usr/src/app/rflink2mqtt.py

RUN chmod 755 /usr/src/app/rflink2mqtt.py

ENV USB_INTERFACE=/dev/ttyACM0
ENV MQTT_SERVER=mosquitto

ENTRYPOINT [ "python3", "-u", "rflink2mqtt.py" ]

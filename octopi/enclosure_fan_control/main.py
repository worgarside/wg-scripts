from json import loads
from os import getenv, path, sep
from time import sleep
from traceback import format_exc
from pigpio import pi as rasp_pi, OUTPUT, LOW, HIGH
from dotenv import load_dotenv
from paho.mqtt.client import Client

PROJECT_ROOT = sep.join(path.abspath(path.dirname(__file__)).split(sep)[:-2])

load_dotenv(sep.join([PROJECT_ROOT, '.env']))

MQTT_BROKER_HOST = getenv('HASSPI_LOCAL_IP')
MQTT_TOPIC = '/homeassistant/prusamk3/enclosure_fan_control'
MQTT_USERNAME = getenv('HASS_MQTT_USERNAME')
MQTT_PASSWORD = getenv('HASS_MQTT_PASSWORD')

FAN_PIN = 16

PI = rasp_pi()
PI.set_mode(FAN_PIN, OUTPUT)


def on_message(_, __, msg):
    try:
        payload = msg.payload.decode()

        if payload == 'on':
            PI.write(FAN_PIN, HIGH)
        elif payload == 'off':
            PI.write(FAN_PIN, LOW)
        else:
            raise ValueError(f'Unexpected payload: {payload}')

    except Exception:
        print(format_exc())


def setup_mqtt():
    def on_connect(client, *args):
        client.subscribe(MQTT_TOPIC)

    temp_client = Client()
    temp_client.username_pw_set(username=MQTT_USERNAME, password=MQTT_PASSWORD)
    temp_client.on_connect = on_connect
    temp_client.on_message = on_message
    temp_client.connect(MQTT_BROKER_HOST, 1883, 60)

    return temp_client


def main():
    while True:
        try:
            mqtt_client = setup_mqtt()
            mqtt_client.loop_forever()
        except:
            del mqtt_client
            sleep(60)


if __name__ == '__main__':
    main()
from importlib.util import spec_from_file_location, module_from_spec
from json import dumps
from os import getenv, path
from time import sleep

from dotenv import load_dotenv
from paho.mqtt.client import Client
from pigpio import pi
from wg_utilities.helpers.functions import get_proj_dirs
from wg_utilities.references.constants import WGSCRIPTS as PROJ_NAME

PROJECT_DIR, SECRET_FILES_DIR, ENV_FILE = get_proj_dirs(path.abspath(__file__), PROJ_NAME)

load_dotenv()

MQTT_BROKER_HOST = getenv('HASSPI_LOCAL_IP')
DHT22_GPIO = int(getenv('DHT22_GPIO', '-1'))
MQTT_TOPIC = getenv('DHT22_MQTT_TOPIC')

spec = spec_from_file_location('dht22', '{}utilities/dht22.py'.format(PROJECT_DIR))
DHT22 = module_from_spec(spec)
spec.loader.exec_module(DHT22)


def on_connect(client, userdata, flags, rc):
    client.subscribe(MQTT_TOPIC)


def setup_mqtt():
    temp_client = Client()
    temp_client.on_connect = on_connect
    temp_client.connect(MQTT_BROKER_HOST, 1883, 60)
    return temp_client


def main():
    mqtt_client = setup_mqtt()
    s = DHT22.Sensor(pi(), DHT22_GPIO)
    s.trigger()
    sleep(2)  # DO NOT REMOVE - the sensor needs this delay to read the values
    temp = round(s.temperature(), 2)
    rhum = round(s.humidity(), 2)
    mqtt_client.publish(MQTT_TOPIC, payload=dumps({'temperature': temp, 'humidity': rhum}))


if __name__ == '__main__':
    main()

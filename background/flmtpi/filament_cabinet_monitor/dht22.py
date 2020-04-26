from importlib.util import spec_from_file_location, module_from_spec
# from json import dumps
from os import getenv, path
from pprint import pprint
from time import sleep

# from dotenv import load_dotenv
# from paho.mqtt.client import Client
from pigpio import pi
# from wg_utilities.helpers.functions import get_proj_dirs
# from wg_utilities.references.constants import WGSCRIPTS as PROJ_NAME

# PROJECT_DIR, SECRET_FILES_DIR, ENV_FILE = get_proj_dirs(path.abspath(__file__), PROJ_NAME)
#
# load_dotenv(ENV_FILE)

# MQTT_BROKER_HOST = getenv('HASSPI_LOCAL_IP')
DHT22_GPIO = 17  # int(getenv('DHT22_GPIO', '-1'))
# MQTT_TOPIC = '/homeassistant/flmtpi/dht22'
# MQTT_USERNAME = getenv('MQTT_USERNAME')
# MQTT_PASSWORD = getenv('MQTT_PASSWORD')

SPEC = spec_from_file_location('dht22', f"{'/'.join(path.abspath(__file__).split('/')[:-1])}/dht22_lib.py")
DHT22 = module_from_spec(SPEC)
SPEC.loader.exec_module(DHT22)


def on_connect(client, *args):
    client.subscribe(MQTT_TOPIC)


def setup_mqtt():
    temp_client = Client()
    temp_client.username_pw_set(username=MQTT_USERNAME, password=MQTT_PASSWORD)
    temp_client.on_connect = on_connect
    temp_client.connect(MQTT_BROKER_HOST, 1883, 60)
    return temp_client


def main():
    try:
        mqtt_client = setup_mqtt()
        mqtt_connected = True
    except OSError:
        mqtt_connected = False

    sensor = DHT22.Sensor(pi(), DHT22_GPIO)
    sensor.trigger()
    sleep(2)  # DO NOT REMOVE - the sensor needs this delay to read the values
    temp = round(sensor.temperature(), 2) if sensor.temperature() > -273 else None
    rhum = round(sensor.humidity(), 2) if sensor.humidity() > 0 else None

    payload = {'temperature': temp, 'humidity': rhum}

    # if mqtt_connected:
    #     mqtt_client.publish(MQTT_TOPIC, payload=dumps(payload))

    pprint(payload)

if __name__ == '__main__':
    main()

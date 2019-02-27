from json import dumps
from os import popen, path, getenv, getloadavg
from socket import gethostname
from warnings import warn

from dotenv import load_dotenv
from paho.mqtt.client import Client
from pigpio import pi as rasp_pi, OUTPUT
from psutil import disk_usage, virtual_memory, cpu_percent
from wg_utilities.helpers.functions import get_proj_dirs
from wg_utilities.references.constants import WGSCRIPTS as PROJ_NAME

PROJECT_DIR, SECRET_FILES_DIR, ENV_FILE = get_proj_dirs(path.abspath(__file__), PROJ_NAME)

load_dotenv(ENV_FILE)

MQTT_BROKER_HOST = getenv('HASSPI_LOCAL_IP')
MQTT_STATS_TOPIC = f'/homeassistant/{gethostname()}/stats'
MQTT_FAN_TOPIC = f'/homeassistant/{gethostname()}/fan'
MIN_CPU_TEMP_THRESHOLD = float(getenv('MIN_CPU_TEMP_THRESHOLD', -999))


def setup_mqtt_fan():
    def on_connect(client, userdata, flags, rc):
        client.subscribe(MQTT_FAN_TOPIC)

    temp_client = Client()
    temp_client.on_connect = on_connect
    temp_client.connect(MQTT_BROKER_HOST, 1883, 60)
    return temp_client


def control_fan(temp, pin_out):
    for k, v in {'MIN_CPU_TEMP_THRESHOLD': MIN_CPU_TEMP_THRESHOLD, 'PIN_OUT': pin_out}.items():
        if v == -999:
            warn("ENV VAR '{}' not set. Not controlling fan.".format(k))
            return

    pi = rasp_pi()
    pi.set_mode(pin_out, OUTPUT)
    pi.write(pin_out, temp > MIN_CPU_TEMP_THRESHOLD)
    pi.stop()

    mqtt_client = setup_mqtt_fan()
    mqtt_client.publish(MQTT_FAN_TOPIC, payload=50 if temp > MIN_CPU_TEMP_THRESHOLD else 0)


def get_cpu_temp():
    temp = float(popen('vcgencmd measure_temp').readline().replace('temp=', '').replace("'C", ''))
    control_fan(temp, int(getenv('PI_FAN_GPIO', -999)))
    return temp


def setup_mqtt_stats():
    def on_connect(client, userdata, flags, rc):
        client.subscribe(MQTT_STATS_TOPIC)

    temp_client = Client()
    temp_client.on_connect = on_connect
    temp_client.connect(MQTT_BROKER_HOST, 1883, 60)
    return temp_client


def get_disk_usage_percent():
    return round(disk_usage('/home').percent)


def get_memory_usage():
    return virtual_memory().percent


def get_cpu_usage():
    return round(cpu_percent(interval=None))


def get_load_15m():
    return getloadavg()[2]


def main():
    mqtt_client = setup_mqtt_stats()

    stats = {
        'cpu_usage': get_cpu_usage(),
        'memory_usage': get_memory_usage(),
        'load_15m': get_load_15m(),
        'temperature': get_cpu_temp(),
        'disk_usage_percent': get_disk_usage_percent()
    }

    mqtt_client.publish(MQTT_STATS_TOPIC, payload=dumps(stats))


if __name__ == '__main__':
    main()

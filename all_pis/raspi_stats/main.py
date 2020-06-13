from datetime import datetime
from json import dumps
from os import popen, path, getenv, getloadavg, sep
from socket import gethostname
from warnings import warn

from dotenv import load_dotenv
from paho.mqtt.client import Client
from pigpio import pi as rasp_pi, OUTPUT
from psutil import disk_usage, virtual_memory, cpu_percent
from requests import post
from time import sleep

PROJECT_ROOT = sep.join(path.abspath(path.dirname(__file__)).split(sep)[:-2])

load_dotenv(sep.join([PROJECT_ROOT, '.env']))

MQTT_BROKER_HOST = getenv('HASSPI_LOCAL_IP')
MQTT_STATS_TOPIC = f'/homeassistant/{gethostname()}/stats'
MIN_CPU_TEMP_THRESHOLD = float(getenv('OCTOPI_MIN_CPU_TEMP_THRESHOLD', '-999'))
MQTT_USERNAME = getenv('HASS_MQTT_USERNAME')
MQTT_PASSWORD = getenv('HASS_MQTT_PASSWORD')

FAN_GPIO = int(getenv('OCTOPI_FAN_GPIO', '-999'))
PWN_PINS = [12, 13, 18]
ABS_MAX_CPU_TEMP = 70


def control_fan(temp):
    for k, v in {'MIN_CPU_TEMP_THRESHOLD': MIN_CPU_TEMP_THRESHOLD, 'PIN_OUT': FAN_GPIO}.items():
        if v == -999:
            warn("ENV VAR '{}' not set. Not controlling fan.".format(k))
            return

    pi = rasp_pi()
    pi.set_mode(FAN_GPIO, OUTPUT)

    if FAN_GPIO not in PWN_PINS or temp > ABS_MAX_CPU_TEMP:
        pi.write(FAN_GPIO, temp > MIN_CPU_TEMP_THRESHOLD)
    elif temp > MIN_CPU_TEMP_THRESHOLD:
        percentage_in_threshold_range = (temp - MIN_CPU_TEMP_THRESHOLD) / (ABS_MAX_CPU_TEMP - MIN_CPU_TEMP_THRESHOLD)
        duty_cycle = percentage_in_threshold_range * 255 * 1.25

        if duty_cycle < 255 * 0.5:
            duty_cycle = 255 * 0.5
        elif duty_cycle > 255:
            duty_cycle = 255

        pi.set_PWM_dutycycle(FAN_GPIO, duty_cycle)
    else:
        pi.write(FAN_GPIO, False)

    pi.stop()


def get_cpu_temp():
    temp = float(popen('vcgencmd measure_temp').readline().replace('temp=', '').replace("'C", ''))
    if gethostname() == 'octopi':
        control_fan(temp)
    return temp


def setup_mqtt_stats():
    def on_connect(client, *args):
        client.subscribe(MQTT_STATS_TOPIC)

    try:
        temp_client = Client()
        temp_client.username_pw_set(username=MQTT_USERNAME, password=MQTT_PASSWORD)
        temp_client.on_connect = on_connect
        temp_client.connect(MQTT_BROKER_HOST, 1883, 60)
        return temp_client
    except Exception:
        return


def get_disk_usage_percent():
    return round(disk_usage('/home').percent)


def get_memory_usage():
    return virtual_memory().percent


def get_cpu_usage():
    return round(cpu_percent(interval=None))


def pb_notify(m, t):
    post(
        'https://api.pushbullet.com/v2/pushes',
        headers={
            'Access-Token': getenv('PB_API_KEY'),
            'Content-Type': 'application/json'
        },
        json={
            'body': m,
            'title': t,
            'type': 'note'
        }
    )


def main():
    mqtt_client = None
    while mqtt_client is None:
        mqtt_client = setup_mqtt_stats()
        sleep(10)

    while True:
        try:

            stats = {
                'cpu_usage': get_cpu_usage(),
                'memory_usage': get_memory_usage(),
                'temperature': get_cpu_temp(),
                'disk_usage_percent': get_disk_usage_percent()
            }

            load_1m, load_5m, load_15m = getloadavg()

            stats.update({
                'load_1m': load_1m,
                'load_5m': load_5m,
                'load_15m': load_15m,
            })

            if datetime.now().minute % 15 == 0:
                del mqtt_client

                mqtt_client = setup_mqtt_stats()

            mqtt_client.publish(MQTT_STATS_TOPIC, payload=dumps(stats))

            sleep(60)
        except Exception as e:
            del mqtt_client

            mqtt_client = setup_mqtt_stats()

            print(type(e).__name__, e.__str__())


if __name__ == '__main__':
    main()

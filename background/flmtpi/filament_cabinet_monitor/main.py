from datetime import datetime
from importlib.util import spec_from_file_location, module_from_spec
from json import dumps
from os import getenv, path, sep

try:
    from RPi import GPIO
    from dot3k import lcd
except RuntimeError:
    pass
from dotenv import load_dotenv
from math import sin, pi as math_pi
from paho.mqtt.client import Client
from pigpio import pi
from time import sleep

load_dotenv(sep.join([*path.abspath(path.dirname(__file__)).split(sep)[:-3], 'secret_files', '.env']))

DHT22_GPIO = 17
SPEC = spec_from_file_location('dht22', f"{'/'.join(path.abspath(__file__).split('/')[:-1])}/dht22_lib.py")
DHT22 = module_from_spec(SPEC)
SPEC.loader.exec_module(DHT22)

MQTT_TOPIC = '/homeassistant/flmtpi/dht22'
MQTT_USERNAME = getenv('MQTT_USERNAME')
MQTT_PASSWORD = getenv('MQTT_PASSWORD')
MQTT_BROKER_HOST = getenv('HASSPI_LOCAL_IP')

LINES = [
    f"Temp:    %s{chr(223)}C",
    'Humid:   %s%%',
    "Dehum'r: %s",
]


def on_connect(client, *args):
    client.subscribe(MQTT_TOPIC)


def setup_mqtt():
    temp_client = Client()
    temp_client.username_pw_set(username=MQTT_USERNAME, password=MQTT_PASSWORD)
    temp_client.on_connect = on_connect
    temp_client.connect(MQTT_BROKER_HOST, 1883, 60)
    return temp_client


def initial_setup():
    lcd.set_contrast(18)
    lcd.clear()

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(5, GPIO.OUT)
    GPIO.setup(6, GPIO.OUT)
    GPIO.setup(13, GPIO.OUT)

    am2302 = DHT22.Sensor(pi(), DHT22_GPIO)

    return am2302


def get_readings(sensor):
    sensor.trigger()
    sleep(2)  # DO NOT REMOVE - the sensor needs this delay to read the values
    temp = round(sensor.temperature(), 2) if sensor.temperature() > -273 else None
    rhum = round(sensor.humidity(), 2) if sensor.humidity() > 0 else None

    return temp, rhum


def main():
    sensor = initial_setup()

    r = GPIO.PWM(5, 100)
    g = GPIO.PWM(6, 100)
    b = GPIO.PWM(13, 100)

    r.start(0)
    g.start(0)
    b.start(0)

    try:
        mqtt_client = setup_mqtt()
    except OSError:
        mqtt_client = None

    try:
        i = 0
        while True:
            r.ChangeDutyCycle(sin(i + 0) * 50.0 + 50)
            g.ChangeDutyCycle(sin(i + (2 * math_pi / 3)) * 50.0 + 50)
            b.ChangeDutyCycle(sin(i + (4 * math_pi / 3)) * 50.0 + 50)

            temp, rhum = get_readings(sensor)

            content = [temp, rhum, 'OFF']

            for line_num, line in enumerate(LINES):
                lcd.set_cursor_position(0, line_num)
                lcd.write(line % content[line_num])

            if datetime.now().minute % 15 == 0:
                del mqtt_client

                mqtt_client = setup_mqtt()

            mqtt_client.publish(MQTT_TOPIC, payload=dumps({'temperature': temp, 'humidity': rhum}))
            sleep(60)
            i += 1
    except KeyboardInterrupt:
        pass

    r.stop()
    g.stop()
    b.stop()
    GPIO.cleanup()


if __name__ == '__main__':
    main()
    # print(sep.join([*path.abspath(path.dirname(__file__)).split(sep)[:-3], 'secret_files', '.env']))
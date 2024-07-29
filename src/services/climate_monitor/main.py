"""Module to take readings from DHT22 and report them to HA."""

from __future__ import annotations

import platform
from colorsys import hsv_to_rgb
from datetime import datetime
from json import dumps
from logging import WARNING
from time import sleep
from typing import TYPE_CHECKING, Any, Final

from pigpio import pi  # type: ignore[import-untyped]
from wg_utilities.decorators import process_exception
from wg_utilities.devices.dht22 import DHT22Sensor
from wg_utilities.loggers import add_warehouse_handler, get_streaming_logger
from wg_utilities.utils import mqtt

if TYPE_CHECKING:
    from collections.abc import Iterator

LOGGER = get_streaming_logger(__name__)
add_warehouse_handler(LOGGER, level=WARNING)

try:
    from dot3k import lcd as dot3k_lcd  # type: ignore[import-not-found]
    from RPi import GPIO
except ImportError:
    if platform.system() != "Darwin":
        raise

    class dot3k_lcd:  # type: ignore[no-redef]  # noqa: N801
        """Dummy class for lcd import on non-Pi machine."""

        @staticmethod
        def clear() -> None:
            """Dummy function for clearing the LCD."""

        @staticmethod
        def create_animation(anim_pos: int, anim_map: list[Any], frame_rate: int) -> None:
            """Dummy function for creating an animation."""

        @staticmethod
        def create_char(char_pos: int, char_map: list[int]) -> None:
            """Dummy function for creating a character."""

        @staticmethod
        def set_contrast(contrast: int) -> None:
            """Dummy function for setting LCD contracts."""

        @staticmethod
        def set_cursor_offset(offset: int) -> None:
            """Dummy function for setting cursor offset."""

        @staticmethod
        def set_cursor_position(column: int, row: int) -> None:
            """Dummy function for setting cursor position."""

        @staticmethod
        def update_animations() -> None:
            """Dummy function for updating animations."""

        @staticmethod
        def write(value: str) -> None:
            """Dummy function for writing to the LCD."""

    class GpioPin:
        """Dummy class for lcd import on non-Pi machine."""

        def ChangeDutyCycle(  # noqa: N802
            self,
            value: float,
        ) -> None:
            """Dummy function."""

        def start(self, value: int) -> None:
            """Dummy function."""

        def stop(self) -> None:
            """Dummy function."""

    class GPIO:  # type: ignore[no-redef]
        """Dummy class for lcd import on non-Pi machine."""

        BCM = 11
        OUT = 0

        @staticmethod
        def cleanup() -> None:
            """Dummy function."""

        @staticmethod
        def setmode(mode: int) -> None:
            """Dummy function."""

        @staticmethod
        def setup(pin: int, mode: int) -> None:
            """Dummy function."""

        @staticmethod
        def PWM(  # noqa: N802
            pin: int,
            mode: int,
        ) -> GpioPin:
            """Dummy function."""
            _ = pin, mode
            return GpioPin()


LOOP_DELAY_SECONDS = 30

DHT22_PIN = 17

RED_PIN = 5
GREEN_PIN = 6
BLUE = 13

TEMP_LINE = f"Temp:  {{0:.1f}}{chr(223)}C"
HUMID_LINE = "Humid: {0:.2f}%"


class DisplayOTron:
    """Class for writing to Pimoroni's Display-O-Tron 3000."""

    LCD = dot3k_lcd

    LINE_COUNT: Final[int] = 3

    MAX_LINE_LENGTH: Final[int] = 16

    @process_exception(logger=LOGGER)
    def write_line(
        self,
        line_num: int,
        content: str,
        *,
        force_truncate: bool = True,
    ) -> None:
        """Write a message to a specific line.

        Args:
            line_num (int): which line to write to
            content (str): the content to output on the LCD
            force_truncate (bool): truncate the line, or raise an error for long lines
             if True

        Raises:
            ValueError: if the line number is invalid
            ValueError: if the content is too long
        """
        if line_num not in (0, 1, 2):
            raise ValueError(
                f"Unexpected line number ({line_num}), expected in range 0-2",
            )

        if len(content) > self.MAX_LINE_LENGTH:
            if force_truncate:
                content = content[: self.MAX_LINE_LENGTH]
            else:
                raise ValueError(
                    f"Content is too long ({len(content)} chars), "
                    f"should be <= {self.MAX_LINE_LENGTH}",
                )

        self.LCD.set_cursor_position(0, line_num)
        self.LCD.write(content.ljust(self.MAX_LINE_LENGTH))

    @process_exception(logger=LOGGER)
    def write_lines(self, lines: list[str], *, wipe_null: bool = False) -> None:
        """Write multiple lines to the LCD.

        Args:
            lines (list): a list of content
            wipe_null (bool): will wipe lines that are None if true, otherwise leaves
             them untouched

        Raises:
            ValueError: if the number of lines to write != 3
        """
        if len(lines) != self.LINE_COUNT:
            raise ValueError(
                f"Unexpected number of lines to write ({len(lines)}, expected length 3",
            )

        for i, line in enumerate(lines):
            if not line and wipe_null is False:
                continue

            self.write_line(line_num=i, content=line or "")


@process_exception(logger=LOGGER)
def rgb_generator(
    num_steps: int = int(86400 / LOOP_DELAY_SECONDS),
) -> Iterator[tuple[float, ...]]:
    """Generator for creating RGB values in order to cycle through the colours.

    Args:
        num_steps (int): the number of steps to run through the colours

    Yields:
        tuple(float): a tuple of RGB intensities(?)
    """
    hue = 0.0
    step_val = 1.0 / num_steps

    while True:
        rgb = hsv_to_rgb(hue, 1, 1)
        hue += step_val
        hue %= 1.0  # cap hue at 1.0

        yield tuple(v * 100 for v in rgb)


@process_exception(logger=LOGGER)
def main() -> None:
    """Takes temp/humidity readings, writes them to the LCD, uploads them to HA."""
    color = rgb_generator()

    dot3k_lcd.set_contrast(18)
    dot3k_lcd.clear()

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(5, GPIO.OUT)
    GPIO.setup(6, GPIO.OUT)
    GPIO.setup(13, GPIO.OUT)

    dht22 = DHT22Sensor(pi(), DHT22_PIN)

    red = GPIO.PWM(5, 100)
    green = GPIO.PWM(6, 100)
    blue = GPIO.PWM(13, 100)

    red.start(0)
    green.start(0)
    blue.start(0)

    screen = DisplayOTron()

    try:
        while True:
            r_val, g_val, b_val = next(color)

            red.ChangeDutyCycle(r_val)
            green.ChangeDutyCycle(g_val)
            blue.ChangeDutyCycle(b_val)

            dht22.trigger()
            screen.write_lines(
                [
                    datetime.now().strftime("%a, %-d %b %Y"),  # noqa: DTZ005
                    TEMP_LINE.format(dht22.temperature),
                    HUMID_LINE.format(dht22.humidity),
                ],
            )

            mqtt.CLIENT.publish(
                f"/homeassistant/{mqtt.HOSTNAME}/dht22",
                payload=dumps(
                    {
                        "temperature": round(dht22.temperature, 2),
                        "humidity": round(dht22.humidity, 2),
                    },
                ),
                qos=0,
                retain=False,
            )

            sleep(LOOP_DELAY_SECONDS)

    except Exception:
        dot3k_lcd.clear()
        red.stop()
        green.stop()
        blue.stop()
        GPIO.cleanup()
        raise


if __name__ == "__main__":
    main()

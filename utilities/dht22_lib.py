from time import time, sleep

from pigpio import PUD_OFF, EITHER_EDGE, tickDiff, LOW, INPUT


class Sensor:
    def __init__(self, pi_obj, gpio, led=None, power=None):
        self.pi = pi_obj
        self.gpio = gpio
        self.led = led
        self.power = power

        if self.power is not None:
            self.pi.write(self.power, 1)  # Switch Sensor on.
            sleep(2)

        self.powered = True

        self.cb = None

        self.bad_CS = 0  # Bad checksum count.
        self.bad_SM = 0  # Short message count.
        self.bad_MM = 0  # Missing message count.
        self.bad_SR = 0  # Sensor reset count.

        # Power cycle if timeout > MAX_TIMEOUTS.
        self.no_response = 0
        self.MAX_NO_RESPONSE = 2

        self.rhum = -999
        self.temp = -999

        self.tov = None

        self.high_tick = 0
        self.bit = 40

        self.pi.set_pull_up_down(self.gpio, PUD_OFF)

        self.pi.set_watchdog(self.gpio, 0)  # Kill any watchdogs.

        self.cb = self.pi.callback(self.gpio, EITHER_EDGE, self._cb)

    def _cb(self, _, level, tick):
        """
        Accumulate the 40 data bits.  Format into 5 bytes, humidity high,
        humidity low, temperature high, temperature low, checksum.
        """
        diff = tickDiff(self.high_tick, tick)

        if level == 0:

            # Edge length determines if bit is 1 or 0.

            if diff >= 50:
                val = 1
                if diff >= 200:  # Bad bit?
                    self.CS = 256  # Force bad checksum.
            else:
                val = 0

            if self.bit >= 40:  # Message complete.
                self.bit = 40

            elif self.bit >= 32:  # In checksum byte.
                self.CS = (self.CS << 1) + val

                if self.bit == 39:

                    # 40th bit received.

                    self.pi.set_watchdog(self.gpio, 0)

                    self.no_response = 0

                    total = self.hH + self.hL + self.tH + self.tL

                    if (total & 255) == self.CS:  # Is checksum ok?

                        self.rhum = ((self.hH << 8) + self.hL) * 0.1

                        if self.tH & 128:  # Negative temperature.
                            mult = -0.1
                            self.tH = self.tH & 127
                        else:
                            mult = 0.1

                        self.temp = ((self.tH << 8) + self.tL) * mult

                        self.tov = time()

                        if self.led is not None:
                            self.pi.write(self.led, 0)

                    else:

                        self.bad_CS += 1

            elif self.bit >= 24:  # in temp low byte
                self.tL = (self.tL << 1) + val

            elif self.bit >= 16:  # in temp high byte
                self.tH = (self.tH << 1) + val

            elif self.bit >= 8:  # in humidity low byte
                self.hL = (self.hL << 1) + val

            elif self.bit >= 0:  # in humidity high byte
                self.hH = (self.hH << 1) + val

            else:  # header bits
                pass

            self.bit += 1

        elif level == 1:
            self.high_tick = tick
            if diff > 250000:
                self.bit = -2
                self.hH = 0
                self.hL = 0
                self.tH = 0
                self.tL = 0
                self.CS = 0

        else:  # level == pigpio.TIMEOUT:
            self.pi.set_watchdog(self.gpio, 0)
            if self.bit < 8:  # Too few data bits received.
                self.bad_MM += 1  # Bump missing message count.
                self.no_response += 1
                if self.no_response > self.MAX_NO_RESPONSE:
                    self.no_response = 0
                    self.bad_SR += 1  # Bump Sensor reset count.
                    if self.power is not None:
                        self.powered = False
                        self.pi.write(self.power, 0)
                        sleep(2)
                        self.pi.write(self.power, 1)
                        sleep(2)
                        self.powered = True
            elif self.bit < 39:  # Short message received.
                self.bad_SM += 1  # Bump short message count.
                self.no_response = 0

            else:  # Full message received.
                self.no_response = 0

    def temperature(self):
        """Return current temperature."""
        return self.temp

    def humidity(self):
        """Return current relative humidity."""
        return self.rhum

    def trigger(self):
        """Trigger a new relative humidity and temperature reading."""
        if self.powered:
            if self.led is not None:
                self.pi.write(self.led, 1)

            self.pi.write(self.gpio, LOW)
            sleep(0.017)  # 17 ms
            self.pi.set_mode(self.gpio, INPUT)
            self.pi.set_watchdog(self.gpio, 200)

    def cancel(self):
        """Cancel the DHT22 Sensor."""

        self.pi.set_watchdog(self.gpio, 0)

        if self.cb is not None:
            self.cb.cancel()
            self.cb = None
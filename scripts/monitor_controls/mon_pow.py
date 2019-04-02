from time import sleep
from pigpio import pi as rasp_pi, OUTPUT

PIN_OUT = 18


def main():
    pi = rasp_pi()
    pi.set_mode(PIN_OUT, OUTPUT)

    pi.write(PIN_OUT, 1)
    sleep(0.1)
    pi.write(PIN_OUT, 0)
    pi.stop()


def user_help():
    """
    A helper function which outputs any extra information about your script as well as returns expected args
    :returns: a dictionary of argument keys and descriptions to be printed in the same way by every script
    """
    author = 'Will Garside'
    description = 'Toggles the laptop screen power. Requires the circuit created in Schematic_pow.fzz'
    expected_args = {}
    env_list = {}

    return author, description, expected_args, env_list


if __name__ == '__main__':
    main()

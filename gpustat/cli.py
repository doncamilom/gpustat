import os
import sys
import time

from blessed import Terminal

from gpustat import __version__
from gpustat.core import GPUStatCollection


def print_gpustat(*, json=False, debug=False, **kwargs):
    '''Display the GPU query results into standard output.'''
    try:
        gpu_stats = GPUStatCollection.new_query(debug=debug)
    except Exception as e:
        sys.stderr.write('Error on querying NVIDIA devices.'
                         ' Use --debug flag for details\n')
        if debug:
            try:
                import traceback
                traceback.print_exc(file=sys.stderr)
            except Exception:
                # NVMLError can't be processed by traceback:
                #   https://bugs.python.org/issue28603
                # as a workaround, simply re-throw the exception
                raise e
        sys.exit(1)

    if json:
        gpu_stats.print_json(sys.stdout)
    else:
        gpu_stats.print_formatted(sys.stdout, **kwargs)


def loop_gpustat(interval=1.0, **kwargs):
    term = Terminal()

    with term.fullscreen():
        while 1:
            try:
                query_start = time.time()

                # Move cursor to (0, 0) but do not restore original cursor loc
                print(term.move(0, 0), end='')
                print_gpustat(eol_char=term.clear_eol + os.linesep, **kwargs)
                print(term.clear_eos, end='')

                query_duration = time.time() - query_start
                sleep_duration = interval - query_duration
                if sleep_duration > 0:
                    time.sleep(sleep_duration)
            except KeyboardInterrupt:
                return 0


def main(*argv):
    if not argv:
        argv = list(sys.argv)

    # attach SIGPIPE handler to properly handle broken pipe
    try:  # sigpipe not available under windows. just ignore in this case
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except Exception as e:
        pass
    # arguments to gpustat
    import argparse
    parser = argparse.ArgumentParser()

    def nonnegative_int(value):
        value = int(value)
        if value < 0:
            raise argparse.ArgumentTypeError(
                "Only non-negative integers are allowed.")
        return value

    parser_color = parser.add_mutually_exclusive_group()
    parser_color.add_argument('--force-color', '--color', action='store_true',
                              help='Force to output with colors')
    parser_color.add_argument('--no-color', action='store_true',
                              help='Suppress colored output')
    parser.add_argument('-a', '--show-all', action='store_true',
                        help='Display all gpu properties above')

    parser.add_argument('-c', '--show-cmd', action='store_true',
                        help='Display cmd name of running process')
    parser.add_argument(
        '-f', '--show-full-cmd', action='store_true', default=False,
        help='Display full command and cpu stats of running process'
    )
    parser.add_argument('-u', '--show-user', action='store_true',
                        help='Display username of running process')
    parser.add_argument('-p', '--show-pid', action='store_true',
                        help='Display PID of running process')
    parser.add_argument('-F', '--show-fan-speed', '--show-fan',
                        action='store_true', help='Display GPU fan speed')
    parser.add_argument(
        '-e', '--show-codec', nargs='?', const='enc,dec', default='',
        choices=['', 'enc', 'dec', 'enc,dec'],
        help='Show encoder/decoder utilization'
    )
    parser.add_argument(
        '-P', '--show-power', nargs='?', const='draw,limit',
        choices=['', 'draw', 'limit', 'draw,limit', 'limit,draw'],
        help='Show GPU power usage or draw (and/or limit)'
    )
    parser.add_argument('--json', action='store_true', default=False,
                        help='Print all the information in JSON format')
    parser.add_argument(
        '-i', '--interval', '--watch', nargs='?', type=float, default=0,
        help='Use watch mode if given; seconds to wait between updates'
    )
    parser.add_argument(
        '--no-header', dest='show_header', action='store_false', default=True,
        help='Suppress header message'
    )
    parser.add_argument(
        '--gpuname-width', type=nonnegative_int, default=None,
        help='The width at which GPU names will be displayed.'
    )
    parser.add_argument(
        '--debug', action='store_true', default=False,
        help='Allow to print additional informations for debugging.'
    )
    parser.add_argument(
        '--no-processes', dest='no_processes', action='store_true',
        help='Hide memory ussage from individual processes.'
    )
    parser.add_argument('-v', '--version', action='version',
                        version=('gpustat %s' % __version__))
    args = parser.parse_args(argv[1:])
    if args.show_all:
        args.show_cmd = True
        args.show_user = True
        args.show_pid = True
        args.show_fan_speed = True
        args.show_codec = 'enc,dec'
        args.show_power = 'draw,limit'
    del args.show_all

    if args.interval is None:  # with default value
        args.interval = 1.0
    if args.interval > 0:
        args.interval = max(0.1, args.interval)
        if args.json:
            sys.stderr.write("Error: --json and --interval/-i "
                             "can't be used together.\n")
            sys.exit(1)

        loop_gpustat(**vars(args))
    else:
        del args.interval
        print_gpustat(**vars(args))


if __name__ == '__main__':
    main(*sys.argv)

#!/usr/bin/env python

"""
the gpustat script :)

@author Jongwook Choi
@url https://github.com/wookayin/gpustat
"""

from __future__ import print_function
from subprocess import check_output, CalledProcessError
from datetime import datetime
from collections import OrderedDict, defaultdict
try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO
import sys
import locale
import platform

__version__ = '0.2.0.dev'


class ANSIColors:
    RESET   = '\033[0m'
    WHITE   = '\033[1m'
    RED     = '\033[0;31m'
    GREEN   = '\033[0;32m'
    YELLOW  = '\033[0;33m'
    BLUE    = '\033[0;34m'
    MAGENTA = '\033[0;35m'
    CYAN    = '\033[0;36m'
    GRAY        = '\033[1;30m'
    BOLD_RED    = '\033[1;31m'
    BOLD_GREEN  = '\033[1;32m'
    BOLD_YELLOW = '\033[1;33m'

    @staticmethod
    def wrap(color, msg):
        return (color + msg + ANSIColors.RESET)


class GPUStat(object):

    def __init__(self, entry):
        if not isinstance(entry, dict):
            raise TypeError('entry should be a dict, {} given'.format(type(entry)))
        self.entry = entry
        self.processes = []

    def __repr__(self):
        return self.print_to(StringIO()).getvalue()

    def print_to(self, fp,
                 with_colors=True,
                 show_cmd=False,
                 show_user=False,
                 show_pid=False,
                 gpuname_width=16
                 ):
        # color settings
        colors = {}
        colors['C0'] = ANSIColors.RESET
        colors['C1'] = ANSIColors.CYAN
        colors['CName'] = ANSIColors.BLUE
        colors['CTemp'] = ANSIColors.RED \
                            if int(self.entry['temperature.gpu']) < 50 \
                            else ANSIColors.BOLD_RED
        colors['CMemU'] = ANSIColors.BOLD_YELLOW
        colors['CMemT'] = ANSIColors.YELLOW
        colors['CMemP'] = ANSIColors.YELLOW
        colors['CUser'] = ANSIColors.GRAY
        colors['CUtil'] = ANSIColors.GREEN \
                            if int(self.entry['utilization.gpu']) < 30 \
                            else ANSIColors.BOLD_GREEN

        if not with_colors:
            for k in list(colors.keys()):
                colors[k] = ''

        # build one-line display information
        reps = ("%(C1)s[{entry[index]}]%(C0)s %(CName)s{entry[name]:{gpuname_width}}%(C0)s |" +
                "%(CTemp)s{entry[temperature.gpu]:>3}'C%(C0)s, %(CUtil)s{entry[utilization.gpu]:>3} %%%(C0)s | " +
                "%(C1)s%(CMemU)s{entry[memory.used]:>5}%(C0)s / %(CMemT)s{entry[memory.total]:>5}%(C0)s MB"
                ) % colors
        reps = reps.format(entry=self.entry,
                           gpuname_width=gpuname_width)
        reps += " |"

        def process_repr(p):
            r = ''
            if not show_cmd or show_user:
                r += "{CUser}{}{C0}".format(p['user'], **colors)
            if show_cmd:
                if r: r += ':'
                r += "{C1}{}{C0}".format(p.get('comm', p['pid']), **colors)

            if show_pid: r += ("/%s" % p['pid'])
            r += '({CMemP}{}M{C0})'.format(p['used_memory'], **colors)
            return r

        for p in self.processes:
            reps += ' ' + process_repr(p)

        fp.write(reps)
        return fp

    @property
    def uuid(self):
        return self.entry['uuid']

    def add_process(self, p):
        self.processes.append(p)
        return self


class GPUStatCollection(object):

    def __init__(self, gpu_list):
        self.gpus = OrderedDict()
        for g in gpu_list:
            self.gpus[g.uuid] = g

        # attach process information (owner, pid, etc.)
        self.update_process_information()

        # attach additional system information
        self.hostname = platform.node()
        self.query_time = datetime.now()

    @staticmethod
    def new_query():
        # 1. get the list of gpu and status
        gpu_query_columns = ('index', 'uuid', 'name', 'temperature.gpu',
                             'utilization.gpu', 'memory.used', 'memory.total')
        gpu_list = []

        smi_output = check_output(
            r'nvidia-smi --query-gpu={query_cols} --format=csv,noheader,nounits'.format(
                query_cols=','.join(gpu_query_columns)
            ), shell=True).decode().strip()

        for line in smi_output.split('\n'):
            if not line: continue
            query_results = line.split(',')

            g = GPUStat({col_name: col_value.strip() for
                         (col_name, col_value) in zip(gpu_query_columns, query_results)
                         })
            gpu_list.append(g)

        return GPUStatCollection(gpu_list)

    @staticmethod
    def running_processes():
        # 1. collect all running GPU processes
        gpu_query_columns = ('gpu_uuid', 'pid', 'used_memory')
        smi_output = check_output(
            r'nvidia-smi --query-compute-apps={query_cols} --format=csv,noheader,nounits'.format(
                query_cols=','.join(gpu_query_columns)
            ), shell=True).decode()

        process_entries = []
        for line in smi_output.split('\n'):
            if not line: continue
            query_results = line.split(',')
            process_entry = dict({col_name: col_value.strip() for
                                  (col_name, col_value) in zip(gpu_query_columns, query_results)
                                  })
            process_entries.append(process_entry)

        pid_map = {int(e['pid']) : None for e in process_entries}

        # 2. map pid to username, etc.
        if pid_map:
            pid_output = check_output('ps -o {} -p {}'.format(
                'pid,user,comm',
                ','.join(map(str, pid_map.keys()))
            ), shell=True).decode().strip()
            for line in pid_output.split('\n'):
                if (not line) or 'PID' in line: continue
                pid, user, comm = line.split()[:3]
                pid_map[int(pid)] = {
                    'user' : user,
                    'comm' : comm
                }

        # 3. add some process information to each process_entry
        for process_entry in process_entries[:]:
            pid = int(process_entry['pid'])
            if pid_map[pid] is None:
                # !?!? this pid is listed up in nvidia-smi's query result,
                # but actually seems not to be a valid running process. ignore!
                process_entries.remove(process_entry)
                continue

            process_entry.update(pid_map[pid])

        return process_entries

    def update_process_information(self):
        processes = self.running_processes()
        for p in processes:
            try:
                g = self.gpus[p['gpu_uuid']]
            except KeyError:
                # ignore?
                pass
            g.add_process(p)
        return self

    def __repr__(self):
        s = 'GPUStatCollection(host=%s, [\n' % self.hostname
        s += '\n'.join('  ' + str(g) for g in self.gpus)
        s += '\n])'
        return s

    def __len__(self):
        return len(self.gpus)

    def __iter__(self):
        return iter(self.gpus.values())

    def __getitem__(self, index):
        return list(self.gpus.values())[index]


    def print_formatted(self, fp=sys.stdout, no_color=False,
                        show_cmd=False, show_user=False, show_pid=False,
                        ):
        # header
        time_format = locale.nl_langinfo(locale.D_T_FMT)
        header_msg = '%(WHITE)s{hostname}%(RESET)s  {timestr}'.format(**{
            'hostname' : self.hostname,
            'timestr' : self.query_time.strftime(time_format)

        }) % (defaultdict(str) if no_color else ANSIColors.__dict__)

        print(header_msg)

        # body
        gpuname_width = max([16] + [len(g.entry['name']) for g in self])
        for g in self:
            g.print_to(fp,
                       with_colors=not no_color,
                       show_cmd=show_cmd,
                       show_user=show_user,
                       show_pid=show_pid,
                       gpuname_width=gpuname_width)
            fp.write('\n')

        fp.flush()


def self_test():
    gpu_stats = GPUStatCollection.new_query()
    print('# of GPUS:', len(gpu_stats))
    for g in gpu_stats:
        print(g)

    process_entries = GPUStatCollection.running_processes()
    print('---Entries---')
    print(process_entries)

    print('-------------')


def new_query():
    '''
    Obtain a new GPUStatCollection instance by querying nvidia-smi
    to get the list of GPUs and running process information.
    '''
    return GPUStatCollection.new_query()


def print_gpustat(no_color=False,
                  show_cmd=False,
                  show_user=False,
                  show_pid=False,
                  ):
    '''
    Display the GPU query results into standard output.
    '''
    try:
        gpu_stats = GPUStatCollection.new_query()
    except CalledProcessError:
        sys.stderr.write('Error on calling nvidia-smi\n')
        sys.exit(1)

    gpu_stats.print_formatted(sys.stdout,
                              no_color=no_color,
                              show_cmd=show_cmd,
                              show_user=show_user,
                              show_pid=show_pid,
                              )


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-color', action='store_true',
                        help='Suppress colored output')
    parser.add_argument('-c', '--show-cmd', action='store_true',
                        help='Display cmd name of running process')
    parser.add_argument('-u', '--show-user', action='store_true',
                        help='Display username of running process')
    parser.add_argument('-p', '--show-pid', action='store_true',
                        help='Display PID of running process')
    parser.add_argument('-v', '--version', action='version',
                        version=__version__)
    args = parser.parse_args()

    print_gpustat(**vars(args))

if __name__ == '__main__':
    main()

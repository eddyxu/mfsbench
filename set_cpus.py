#!/usr/bin/env python3
#
# Lei Xu <eddyxu@gmail.com>

"""Manually set CPU cores online or offline
"""

from __future__ import print_function
import optparse
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'pyro'))
from pyro import osutil

POSSIBLE_CPUS = osutil.get_all_cpus()


def find_max_continous_sequence(array, start):
    """Find a continous sequence of numbers in the array.

    @param array a list of numbers.
    @param start the start index to do the sequence lookup.
    """
    pos = start
    while pos + 1 < len(array):
        if not array[pos] + 1 == array[pos + 1]:
            break
        pos += 1
    if pos + 1 == len(array):
        return array[start:]
    return array[start:pos + 1]


def shorten_cores(cores):
    """Return a shorten presentation of cores
    """
    cores = sorted(list(cores))
    if len(cores) == 0:
        return ''
    core_buffer = ''
    start = 0
    while start < len(cores):
        cont_seq = find_max_continous_sequence(cores, start)
        start += len(cont_seq)
        if len(cont_seq) > 1:
            core_buffer += ',%d-%d' % (cont_seq[0], cont_seq[-1])
        else:
            core_buffer += ',%d' % cont_seq[0]
    return core_buffer[1:]


def set_cpu(core, online, **kwargs):
    """Set cpu online or offline
    @param core the core id
    @param online True to set a core online, False to set a core offline
    @param kwargs dry={True,False}
    """
    assert type(online) == bool
    if core == 0:
        if not online:
            raise ValueError("Can not set cpu0 offline")
        return

    online_path = '/sys/devices/system/cpu/cpu%d/online' % core
    if 'dry' in kwargs and kwargs['dry']:
        print("DRY-RUN: write %d to %s" % (online, online_path))
        return
    os.system('echo %d > %s' % (online, online_path))


def reset():
    """Reset all POSSIBLE_CPUS cpu online
    """
    for cpu_id in POSSIBLE_CPUS:
        set_cpu(cpu_id, True)


def list_cpus():
    """List all online and offline CPUs
    """
    online_cpus = osutil.get_online_cpus()
    offline_cpus = POSSIBLE_CPUS - online_cpus
    print("Online: CPU ", shorten_cores(online_cpus))
    print("Offline: CPU ", shorten_cores(offline_cpus))


def set_cpus(core_str, **kwargs):
    """Sets the CPU cores online.

    @param core_str a comma separated string, e.g., '3,4-5,12-17'.
    """
    online_cores = osutil.parse_cpus(core_str)
    offline_cores = POSSIBLE_CPUS - online_cores
    for online in online_cores:
        set_cpu(online, True, **kwargs)
    for offline in offline_cores:
        set_cpu(offline, False, **kwargs)


def main():
    """Set CPUs offline/online
    """
    parser = optparse.OptionParser(
        usage='Usage: %prog [options] [cpu range|cpu ids]')
    parser.add_option('--dry', action='store_true', default=False,
                      help='dry run')
    parser.add_option('-r', '--reset', action='store_true', default=False,
                      help='reset all cores to be online')
    parser.add_option('-l', '--list', action='store_true', default=False,
                      help='list all online and offline cpus')
    options, args = parser.parse_args()

    if os.getuid() != 0:
        print("Must run this script with root privilege.", file=sys.stderr)
        sys.exit(1)

    if options.reset:
        reset()
    elif options.list:
        list_cpus()
    elif not args:
        parser.print_help()
        sys.exit(1)
    else:
        set_cpus(args[0], dry=options.dry)


if __name__ == '__main__':
    main()

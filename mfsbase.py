#!/usr/bin/env python3
#
# Author: Lei Xu <eddyxu@gmail.com>

"""Base library for manycore filesystem benchmark.
"""

import os
import sys
from subprocess import call, check_output
sys.path.append(os.path.join(os.path.dirname(__file__), 'pyro'))
import pyro


def check_root_or_exit():
    if not os.geteuid() == 0:
        sys.exit("You must run this program with root privilege.")


def clear_cache():
    """Clear system cache.
    """
    check_root_or_exit()
    call('sync')
    call('echo 3 > /proc/sys/vm/drop_caches', shell=True)


def mount(disk, mntpnt, **kwargs):
    """Mount a disk to the mount point.
    """
    check_root_or_exit()
    fs_format = kwargs.get('format', 'ext4')
    call('mkfs.{} {}'.format(fs_format, disk), shell=True)
    call('mount -t {} {} {}'.format(fs_format, disk, mntpnt), shell=True)


def umount(mntpnt):
    """Umount a mounted file system.

    @param mntpnt mount point
    """
    call('umount {}'.format(mntpnt), shell=True)


def umount_all(basedir):
    """Umount all filesystems under the basedir

    Currently it only unmounts the first level of dirs, which means that it
    does not recursively umount filesystems.
    """
    for subdir in os.listdir(basedir):
        mntpnt = os.path.join(basedir, subdir)
        if os.path.ismount(mntpnt):
            umount(mntpnt)


def dump_system_configure():
    """Dump system configurations.
    """
    from pyro import osutil
    import platform as pf
    sys_confs = {}
    sys_confs['node'] = pf.node()
    sys_confs['system'] = pf.system() + " " + pf.release()
    sys_confs['num_cpus'] = len(osutil.get_online_cpus())
    sys_confs['memory'] = osutil.get_total_memory()

    return sys_confs

class Profiler:
    """The interface of Profiler.
    """
    def start(self):
        pass

    def stop(self):
        pass

    def report(self):
        pass

    def dump(self, outfile):
        """Dumps the report to the outfile.
        @param outfile it can be a file object or a string file path.
        """
        if type(outfile) == str:
            with open(outfile, 'w+') as fobj:
                fobj.write(self.report() + '\n')
        else:
            outfile.write(self.report() + '\n')


class LockstatProfiler(Profiler):
    """The Profiler to get /proc/lock_stat data
    """
    def __init__(self):
        self.report_ = ""

    def clear_lockstat(self):
        """Clear the statistics data of kernel lock
        """
        with open('/proc/lock_stat', 'w') as fobj:
            fobj.write('0\n')

    def start(self):
        """Starts to monitor lock stat
        """
        self.clear_lockstat()

    def stop(self):
        """Stops to monitor lock stats and gather the results.
        """
        with open('/proc/lock_stat', 'r') as fobj:
            self.report_ = fobj.read()

    def report(self):
        return self.report_


class ProcStatProfiler(Profiler):
    def __init__(self):
        self.report_ = ""

    def start(self):
        with open('/proc/stat', 'r') as fobj:
            self.before = fobj.readline()

    def stop(self):
        with open('/proc/stat', 'r') as fobj:
            self.after = fobj.readline()

    def report(self):
        """Generates report.
        """
        before_fields = [int(x) for x in self.before.split()[1:]]
        after_fields = [int(x) for x in self.after.split()[1:]]
        return_fields = [str(x - y) for x, y in
                         zip(after_fields, before_fields)]
        return 'cpu ' + ' '.join(return_fields) + '\n'


class PerfProfiler(Profiler):
    """Use linux's perf utility to measure the PMU.
    """
    EVENTS = '-e cycles,cache-misses,LLC-load-misses'
    #EVENTS = '-e cycles'

    def __init__(self, perf='perf', **kwargs):
        """Constructs a PerfProfiler

        @param perf the exective of 'perf'

        Optional parameters:
        @param events the events to be recorded.
        @param vmlinux the kernel image to find symbols.
        @param kallsyms the kallsyms file.
        """
        self.perf = perf
        self.check_avail(perf)
        self.vmlinux = kwargs.get('vmlinux', '')
        self.kallsyms = kwargs.get('kallsyms', '')
        if kwargs.get('events', ''):
            self.EVENTS = '-e ' + kwargs.get('events')

    @staticmethod
    def check_avail(perf=''):
        if call('which {}'.format(perf), shell=True) > 0:
            raise RuntimeError('PerfProfiler can not find perf binary: \'{}\'.'
                               .format(perf))


    def start(self, cmd):
        """Start recording perf events.
        """
        print("Perf record events: {}".format(self.EVENTS))
        return call('{} record {} -a {}'.format(self.perf, self.EVENTS, cmd),
                    shell=True)

    def stop(self):
        """
        """
        options = ''
        if self.vmlinux:
            options += ' -k {}'.format(self.vmlinux)
        if self.kallsyms:
            options += ' --kallsyms={}'.format(self.kallsyms)
        self.report_ = check_output(
            '{} report {} --stdio'.format(self.perf, options),
            shell=True).decode('utf-8')

    def report(self):
        return self.report_


class OProfiler(Profiler):
    """Use oprofiler
    """
    EVENTS = '--event=L3_CACHE_MISSES:500'

    def __init__(self, vmlinux='', events=''):
        self.vmlinux = vmlinux
        if events:
            self.EVENTS = events

    def start(self):
        call('opcontrol --reset', shell=True)
        call('opcontrol --init', shell=True)
        if self.vmlinux:
            call('opcontrol --vmlinux={}'.format(self.vmlinux))
        if self.EVENTS:
            call('opcontrol --setup --separate=none {}' % self.events)
        call('opcontrol --start')

    def stop(self):
        call('opcontrol --dump')
        call('opcontrol --stop')
        self.report_ = check_output('opreport -cl', shell=True).decode('utf-8')

    def report(self):
        return self.report_

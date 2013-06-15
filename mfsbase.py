#!/usr/bin/env python3
#
# Author: Lei Xu <eddyxu@gmail.com>

"""Base library for manycore filesystem benchmark.
"""

import os
import sys
from subprocess import call, Popen


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
            with open(outfile, 'w') as fobj:
                fobj.write(self.report())
        else:
            outfile.write(self.report())


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
    EVENTS = '-e cycles,LLC-load-misses'

    def __init__(self, perf='perf', events=''):
        """Constructs a PerfProfiler

        @param perf the exective of 'perf'
        """
        self.perf = perf
        self.check_avail(perf)
        if events:
            self.EVENTS = events

    @staticmethod
    def check_avail(perf=''):
        if call('which {}'.format(perf), shell=True) > 0:
            raise RuntimeError('PerfProfiler can not find perf binary: \'{}\'.'
                               .format(perf))

    def start(self, cmd):
        """Start recording perf events.
        """
        return call('{} record {} -a {}'.format(self.perf, self.EVENTS, cmd),
                    shell=True)

    def stop(self):
        p = Popen('{} report'.format(self.perf), shell=True)
        self.report_ = p.communicate()[0]

    def report(self):
        return self.report_

#!/usr/bin/env python3
#
# Author: Lei Xu <eddyxu@gmail.com>

"""Base library for manycore filesystem benchmark.
"""

import os
import sys
from subprocess import call

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


class LockstatProfiler:
    def __init__(self):
        self.report_ = ""

    def clear_lockstat(self):
        """Clear the statistics data of kernel lock
        """
        with open('/proc/lock_stat', 'w') as fobj:
            fobj.write('0\n')

    def start(self):
        self.clear_lockstat()

    def stop(self):
        with open('/proc/lock_stat', 'r') as fobj:
            self.report = fobj.readlines()

    def report(self):
        return self.report_

    def dump(self, outfile):
        """Dumps the report to the outfile.
        @param outfile it can be a file object or a string file path.
        """
        if type(outfile) == str:
            with open(outfile) as fobj:
                fobj.write(self.report_)
        else:
            outfile.write(self.report_)

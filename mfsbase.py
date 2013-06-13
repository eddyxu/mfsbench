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
    call('umount {}'.format(mntpnt))

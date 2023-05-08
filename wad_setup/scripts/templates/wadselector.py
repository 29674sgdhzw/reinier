#!/usr/bin/env python
import subprocess
from os import environ, path, makedirs, pathsep
import sys

__version__ = '20170222'

"""
wadselector should be the process that runs the real selector in the background,
because the lua script in orthanc halts orthanc during execution of the lua script 
(https://orthanc.chu.ulg.ac.be/book/users/lua.html : All of these callbacks are 
guaranteed to be invoked in mutual exclusion), meaning that the selector cannot
access orthanc.
"""

if __name__ == "__main__":
    # add some paths so wadselector can be found when called from systemd
    xtrapaths = __XTRAPATHS__
    for p in xtrapaths:
        if not p in environ['PATH']:
            environ['PATH'] =  "{}{}{}".format(p, pathsep, environ['PATH'])

    cmd = [ 'wadselector' ]
    cmd.extend(sys.argv[1:])

    subprocess.Popen(cmd)

"""
reimplementation of platform.dist() since it has disappeared from python 3.8 
and it is needed before pip install distro or apt install python3-distro.
"""
import os
import shlex
def distro():
    result = {}
    fname = "/etc/os-release"
    if os.path.exists(fname):
        with open(fname) as f:
            keyvals = {}
            lexer = shlex.shlex(f, posix=True)
            lexer.whitespace_split = True
            for line in lexer:
                k, v = line.split('=', 1)
                keyvals[k] = v
        result['distro'] = keyvals['ID'].lower()
        result['version'] = keyvals['VERSION_ID'].lower()
        result['name'] = keyvals['PRETTY_NAME']
        return result

    fname = "/etc/lsb-release"
    if os.path.exists(fname):
        with open(fname) as f:
            keyvals = {}
            lexer = shlex.shlex(f, posix=True)
            lexer.whitespace_split = True
            for line in lexer:
                k, v = line.split('=', 1)
                keyvals[k] = v
        result['distro'] = keyvals['DISTRIB_ID'].lower()
        result['version'] = keyvals['DISTRIB_RELEASE'].lower()
        result['name'] = keyvals['DISTRIB_DESCRIPTION']
        return result

    return result

#!/usr/bin/env python
from __future__ import print_function

import os
import argparse
import stat
import errno
import subprocess
import platform
import logging

__version__ = '20190207' 

"""
Changelog:
 20190207: added orthancpluginsroot because was not used for apt!
 20170914: bugfix multiple '-r' arguments defined (removed short hand notations for different ports);
           bugfix pacs_port argument was set to rest_port
 20170503: added ports for PostgreSQL and REST and PACS
 20170215: can be used stand-alone
 20170209: stripped down version of orthanc_setup.py
 
"""

try:
    from .defaults import LOGGERNAME
    from .addtoenv import addtoenv
except:
    from defaults import LOGGERNAME
    from addtoenv import addtoenv
    
logger = logging.getLogger(LOGGERNAME)

def create_folders(installation_root, **kwargs):
    # create needed directories
    result = 'OK'
    msg = ''
    
    logger.info("...creating directory structure...")
    folders = [
        os.path.join(installation_root, 'orthanc', 'db'),
        os.path.join(installation_root, 'orthanc', 'lua'),
        os.path.join(installation_root, 'orthanc', 'plugins'),
        os.path.join(installation_root, 'orthanc', 'bin'),
        os.path.join(installation_root, 'orthanc', 'config'),
        os.path.join(installation_root, 'WAD_QC', 'Logs'),
    ]
    for folder in folders:
        try:
            os.makedirs(folder)
        except OSError as e: 
            if e.errno == errno.EEXIST and os.path.isdir(folder):
                pass
            else:
                result = 'ERROR'
                msg = str(e)

    return result, msg

def copy_replaces(src, dest, inlist, outlist):
    # read the template from src, and write to dest, 
    #   whilst replacing each placeholder in inlist by the one in outlist
    with open(src, mode='r') as f:
        data = f.read()

    for old, new in zip (inlist, outlist):
        data = data.replace(old, new)

    with open(dest, mode='w') as f:
        f.write(data)

def create_scripts(database, **kwargs):
    """
    Create scripts and infiles with proper paths and passwords.
    The database mentioned here is for Orthanc. Right now only PostgreSQL is supported, with a fall-back to
    SQLite if PostgreSQL plugins are not installed. Therefore, the database parameter should be "postgresql".
    """
    # 
    logger.info("...creating proper scripts from templates...")
    result = 'OK'
    msg = ''
    
    installation_root = kwargs['installation_root']
    orthancplugins_root = kwargs.get('orthancplugins_root', installation_root) # if not provided, use WADROOT
    
    templates = os.path.join(os.path.dirname(__file__), 'templates')
    # postgresql support
    if database == 'postgresql':
        inlist = ['__ORTHANCPLUGINSROOT__', '__DEVROOT__', '__PACSPSWD__', '__ODBPSWD__', '__PSQLPORT__', '__RESTPORT__', '__PACSPORT__', '\\']
        outlist = [ orthancplugins_root, installation_root, kwargs['orthanc_pass'], kwargs['orthancdb_pass'], 
                    str(kwargs['pgsql_port']), str(kwargs['rest_port']), str(kwargs['pacs_port']), '/' ]
        copy_replaces(src=os.path.join(templates, 'orthanc_postgresql.json'), 
                      dest=os.path.join(installation_root, 'orthanc', 'config', 'orthanc.json'), 
                      inlist=inlist, 
                      outlist=outlist) 
    else:
        result = 'ERROR'
        msg = 'Requested database type "{}" is unknown. Should be "postgresql" for Orthanc.'.format(database)

    if result == 'ERROR':
        return result, msg

    # lua script and wadselector
    xtra_paths = [ os.path.expanduser('~/.local/bin') ] # make sure wadselector can be found for systemd controlled orthanc
    inlist = ['__WADROOT__', '__XTRAPATHS__']
    outlist = [installation_root, str(xtra_paths)]

    copy_replaces(src=os.path.join(templates, 'wad_onstablestudy.lua'), 
                  dest=os.path.join(installation_root, 'orthanc', 'lua', 'wad_onstablestudy.lua'), 
                  inlist=inlist, 
                  outlist=outlist) 
    copy_replaces(src=os.path.join(templates, 'wadselector.py'), 
                  dest=os.path.join(installation_root, 'orthanc', 'lua', 'wadselector.py'), 
                  inlist=inlist, 
                  outlist=outlist)

    dest=os.path.join(installation_root, 'orthanc', 'lua', 'wadselector.py')
    try: # make selector executable
        os.chmod(dest, os.stat(dest).st_mode | stat.S_IEXEC)
    except Exception as e:
        msg += 'WARNING: cannot make {} executable'.format(os.path.basename(dest))

    # inifiles
    inlist = ['__DEVROOT__', '__IDBPSWD__', '__PACSPSWD__', '__PSQLPORT__', '__RESTPORT__']
    outlist = [installation_root, kwargs['iqcdb_pass'], kwargs['orthanc_pass'], str(kwargs['pgsql_port']), str(kwargs['rest_port'])]
    copy_replaces(src=os.path.join(templates, 'wadconfig_postgresql.ini' if database == 'postgresql' else 'wadconfig.ini'), 
                  dest=os.path.join(installation_root, 'WAD_QC', 'wadconfig.ini'), 
                  inlist=inlist, 
                  outlist=outlist) 
    copy_replaces(src=os.path.join(templates, 'wadsetup.ini'), 
                  dest=os.path.join(installation_root, 'WAD_QC', 'wadsetup.ini'), 
                  inlist=inlist, 
                  outlist=outlist) 

    # make sure this one variable is stored in the environment
    result2, msg2 = addtoenv( {'WADROOT':installation_root} )

    # just add this to the path to make sure all python executables will be found for wadqc pip installed --user
    if not '.local/bin' in os.environ['PATH']:
        result2, msg2 = addtoenv({'PATH': os.path.expanduser('~/.local/bin')})

    return result, msg+msg2

if __name__ == "__main__":
    orthancweb_pass = None
    orthancdb_pass = None
    wadqcdb_pass = None
    pgsql_port = 5432
    rest_port = 8042
    pacs_port = 11112
    installation_root = os.environ.get('WADROOT', None)
    
    # do not run as root! the script will ask for permission if it needs root
    if os.name == 'nt':
        pass
    elif os.geteuid() == 0:
        logger.error("Do not run folders_settings as root! The script will ask you for root permission if it needs it! Exit.")    
        exit(False)

    parser = argparse.ArgumentParser(description='Create WAD-QC folders and scripts and settings')
    parser.add_argument('-r', '--root',
                        default=installation_root,
                        type=str,
                        help='root folder for WAD-QC and Orthanc [{}].'.format(installation_root),
                        dest='installation_root')

    parser.add_argument('-w', '--orthancweb_pass',
                        default=orthancweb_pass,
                        type=str,
                        help='password for REST access to Orthanc [{}].'.format(orthancweb_pass),
                        dest='orthancweb_pass')
    parser.add_argument('-o', '--orthancdb_pass',
                        default=orthancdb_pass,
                        type=str,
                        help='password for access to Orthanc database [{}].'.format(orthancdb_pass),
                        dest='orthancdb_pass')
    parser.add_argument('-p', '--wadqcdb_pass',
                        default=wadqcdb_pass,
                        type=str,
                        help='password for access to WAD-QC database [{}].'.format(wadqcdb_pass),
                        dest='wadqcdb_pass')

    parser.add_argument('--pgsql_port',
                        default=pgsql_port,
                        type=int,
                        help='port for PostgreSQL server [{}].'.format(pgsql_port),
                        dest='pgsql_port')
    parser.add_argument('--rest_port',
                        default=rest_port,
                        type=int,
                        help='port for REST access to Orthanc [{}].'.format(rest_port),
                        dest='rest_port')
    parser.add_argument('--pacs_port',
                        default=pacs_port,
                        type=int,
                        help='port for DICOM node of Orthanc [{}].'.format(pacs_port),
                        dest='pacs_port')
    parser.add_argument('--orthancplugins_root',
                        default=installation_root,
                        type=str,
                        help='root folder for Orthanc plugins (/orthanc/plugins will be added) [{}].'.format(orthancweb_pass),
                        dest='orthancplugins_root')

    args = parser.parse_args()

    if None in [args.installation_root, args.wadqcdb_pass, args.orthancdb_pass, args.orthancweb_pass]:
        print('Error! folders_settings needs --root and --wadqcdb_pass and --orthancdb_pass and --orthancweb_pass. Exit.\n\n')
        parser.print_help()
        exit(False)
    
    installation_root = os.path.abspath(os.path.expanduser(args.installation_root))
    result, msg = create_folders(installation_root)
    if result == "ERROR":
        print(result, msg)
        parser.print_help()
        exit(False)

    result, msg = create_scripts('postgresql', installation_root = installation_root,
                                 orthanc_pass = args.orthancweb_pass, iqcdb_pass = args.wadqcdb_pass, orthancdb_pass = args.orthancdb_pass,
                                 pgsql_port = args.pgsql_port, rest_port = args.rest_port, pacs_port = args.pacs_port, 
                                 orthancplugins_root = args.orthancplugins_root)
    if result == "ERROR":
        print(result, msg)
        parser.print_help()
        exit(False)

    print("Done.")
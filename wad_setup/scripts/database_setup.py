#!/usr/bin/env python
from __future__ import print_function
__version__ = '20170503' 

"""
Changelog:
    20170503: added ports for PostgreSQL
"""

import os
import argparse
import time
import logging
try:
    from .helpers import external_call, port_available
    from .defaults import LOGGERNAME
    from .folders_settings import copy_replaces
except:
    from helpers import external_call, port_available
    from defaults import LOGGERNAME
    from folders_settings import copy_replaces
    
logger = logging.getLogger(LOGGERNAME)

#----config file helpers
def get_dict_from_inifile(inifile):
    # read the inputconfig as a config, and cast it into a dict
    try:
        import configparser
    except ImportError:
        import ConfigParser as configparser

    config = configparser.SafeConfigParser()
    with open(inifile,'r') as f:
        config.readfp(f)

    config_dict = {}
    for section in config.sections():
        config_dict[section] = {}
        for option in config.options(section):
            config_dict[section][option.upper()] = config.get(section, option)
    return config_dict

def get_dict_from_jsonfile(jsonfile):
    import simplejson as json
    import jsmin
    
    with open(jsonfile) as f:
        validjson = jsmin.jsmin(f.read()) # strip comments and stuff from more readable json
    setup = json.loads(validjson)
    return setup

def create_postgresql_datadir(wadroot=None, pgport=5432):
    """
    Create a new PostgreSQL datadir under WADROOT.
    This step is needed before create_databases databases can be called.
    """
    logger = logging.getLogger(LOGGERNAME)
    logger.info('Creating datadir for PostgreSQL...')

    if wadroot is None:
        wadroot = os.environ.get('WADROOT', None)
    if wadroot is None:
        msg = "Cannot create_postgresql_datadir without wadroot! {}".format(e)
        return result, msg

    pgsdata = os.path.join(wadroot, 'pgsql', 'data')

    initdb = 'initdb'

    # find pg bindir; that is where initdb and pg_ctl are located (not always in path).
    pgbindir = None
    cmd = ['pg_config', '--bindir']
    result, msg = external_call(cmd, returnoutput=True)
    if result == "OK":
        pgbindir = msg
        initdb = os.path.join(pgbindir, initdb)

    cmds = [ # [command line], background=True/False
             # set the default auth method for local connections to 'trust' so we can create the databases 
             #   without postgres user password for dev. Later set this to peer.
        ( [initdb, '-D', pgsdata, '-E', 'UTF8', '-U', 'postgres', '--auth-host', 'password', '--auth-local', 'trust'], False), # create database
        ( ['fix_config'], False),
    ]
        
    # enable logging
    src  = os.path.join(pgsdata, 'postgresql.conf')
    dest = src # replace original
    inlist = ["#log_destination = 'stderr'",
              "#logging_collector = off",
              "#log_directory = 'pg_log'",
              "#log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log",
              "#log_rotation_size = 10MB"
              ]
    outlist = ["log_destination = 'stderr'",
               "logging_collector = on",
               "log_directory = 'pg_log'",
               "log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log",
               "log_rotation_size = 10MB"
               ]

    # correct port
    if not pgport == 5432:
        inlist.append("#port = 5432")
        outlist.append("port = {}".format(pgport))

    for cmd,bk in cmds:
        if cmd[0] == 'fix_config':
            copy_replaces(src=src, dest=dest, 
                          inlist=inlist, outlist=outlist) 
            continue

        result, msg = external_call(cmd, returnoutput=True, background=bk)
        
        if bk:
            time.sleep(3)

        mustquit = (not result == "OK")
        if mustquit:
            if 'exists but is not empty' in msg:
                result = "OK"
                logger.warning(msg)
            else:
                errormsg = 'Could not create PostgreSQL datafolder! '
                return result, errormsg+msg
            

    return result, msg

def wait_pgready(pgport):
    """
    helper to wait until postgresql is ready
    """
    pg_ready = 'pg_isready'
    # find pg bindir; that is where initdb and pg_ctl are located (not always in path).
    pgbindir = None
    cmd = ['pg_config', '--bindir']
    result, msg = external_call(cmd, returnoutput=True)
    if result == "OK":
        pgbindir = msg
        pg_ready = os.path.join(pgbindir, pg_ready)

    if os.path.isfile(pg_ready):
        # check if postgres service is running
        # retry for 30 seconds until service is up
        for i in range(1,30):
            result, msg = external_call([pg_ready, '-p', str(pgport)], returnoutput=True)
            if 'no response' in msg or 'rejecting' in msg:
                print(i, msg)
                if i == 30:
                    msg = "PostgreSQL does not (yet) seem to be running on port {}!".format(pgport)
                    return "ERROR", msg
                time.sleep(1)
            else:
                print(msg)
                break
    else:
        # pg_isready does not exist
        logger.info("{} does not exist, will test if postgresql is running by looking if port {} is available.".format(pg_ready, pgport))
        # wait until port is no longer available
        for i in range(1,30):
            result = port_available(pgport)
            if result == True:
                msg = "port {} still available".format(pgport)
                print(i, msg)
                if i == 30:
                    msg = "PostgreSQL does not (yet) seem to be running on port {}!".format(pgport)
                    return "ERROR", msg
                time.sleep(1)
            else:
                msg = "port {} is no longer available, assume PostgreSQL has started. Waiting 5 more seconds...".format(pgport)
                time.sleep(5) # wait some more
                print(msg)
                break

    return "OK", ""


def create_databases(wadroot=None, pgport=5432):
    """
    create databases.
    If installed from apt, skip create_postgresql_datadir.
    use sudo -u postgres before psql commands
    """
    logger = logging.getLogger(LOGGERNAME)
    logger.info('Creating database for WAD-QC and Orthanc...')
    result, msg = ("OK", "")

    if wadroot is None:
        wadroot = os.environ.get('WADROOT', None)
    if wadroot is None:
        result = "ERROR"
        msg = "Cannot create_databases without wadroot! {}".format(e)
        return result, msg

    pg_ctl = 'pg_ctl'
    pg_ready = 'pg_isready'
    psql = 'psql'
    # find pg bindir; that is where initdb and pg_ctl are located (not always in path).
    pgbindir = None
    cmd = ['pg_config', '--bindir']
    result, msg = external_call(cmd, returnoutput=True)
    if result == "OK":
        pgbindir = msg
        pg_ready = os.path.join(pgbindir, pg_ready)
        pg_ctl = os.path.join(pgbindir, pg_ctl)
        psql = os.path.join(pgbindir, psql)

    # check is wadpostgresql is enabled; if not, pgsql needs to be started manually
    using_systemd = True
    cmd = ['systemctl', 'is-enabled', 'wadpostgresql']
    result, msg = external_call(cmd, returnoutput=True)
    if not msg == 'enabled':
        using_systemd = False
        if wadroot is None:
            wadroot = os.environ.get('WADROOT', None)
        if wadroot is None:
            msg = "Cannot create_databases without wadroot! {}".format(e)
            return "ERROR", msg
    
        pgsdata = os.path.join(wadroot, 'pgsql', 'data')

        cmd = [pg_ctl, '-D', pgsdata, 'start'] # start server
        result, msg = external_call(cmd, returnoutput=True, background=True)

        if (not result == "OK"):
            return "ERROR", msg
    
    # check if postgres service is running
    result, msg = wait_pgready(pgport)
    if result == "ERROR":
        return "ERROR", msg

    # get iqc-db password
    inifile = os.path.join(wadroot, 'WAD_QC', 'wadconfig.ini')
    try:
        iqcdb_pass = get_dict_from_inifile(inifile)['iqc-db']['PSWD']
    except Exception as e:
        result = "ERROR"
        msg = "Cannot find password for iqc-db in {}. {}. Exit.\n\n".format(inifile, str(e))
        return result, msg

    # get orthanc-db password
    orthanc_json = os.path.join(wadroot, 'orthanc', 'config', 'orthanc.json')
    try:
        orthancdb_pass = get_dict_from_jsonfile(orthanc_json)['PostgreSQL']['Password']
    except Exception as e:
        result = "ERROR"
        msg = "Cannot find password for orthanc-db in {}. {}. Exit.\n\n".format(orthanc_json, str(e))
        return result, msg


    sqlcmds = [
        "CREATE USER orthanc CREATEDB LOGIN NOSUPERUSER PASSWORD '%s';"%orthancdb_pass,
        "CREATE DATABASE orthanc_db ENCODING 'UTF8' OWNER orthanc;",
        "CREATE USER wadqc CREATEDB LOGIN NOSUPERUSER PASSWORD '%s';"%iqcdb_pass,
        "CREATE DATABASE wadqc_db ENCODING 'UTF8' OWNER wadqc;",
    ]
    
    # check if we need sudo, or that we can do without
    sqltest = "SELECT version();"
    psqlcmd = [psql, '-U', 'postgres', '-d', 'postgres', '-p', str(pgport)]
    result, msg = external_call(psqlcmd+['-c', sqltest], returnoutput=True)
    if result == "ERROR":
        if 'authentication failed for user' in msg:
            psqlcmd = ['sudo', '-u', 'postgres']+psqlcmd
        else:
            return result, msg

    cmds = []
    for sql in sqlcmds:
        cmds.append(psqlcmd+['-c', sql])
            
    for cmd in cmds:
        result, msg = external_call(cmd, returnoutput=True)
        if 'could not flush' in msg:
            result = "OK"
        mustquit = (not result == "OK")
        if mustquit:
            if 'already exists' in msg:
                result = "OK"
            else:
                errormsg = 'Could not create PostgreSQL databases for Orthanc and WAD-QC! '
                return result, errormsg+msg

    # the databases and users are created. set local logic to 'peer'
    pgsdata = os.path.join(wadroot, 'pgsql', 'data')
    src  = os.path.join(pgsdata, 'pg_hba.conf')
    with open(src, "r") as fio:
        hba = fio.readlines()
    with open(src, "w") as fio:
        for line in hba:
            if line.strip().startswith('local'):
                fio.write('# '+ line)
                line = line.replace("trust", "peer")
            fio.write(line)
    
    # restart postgresql for authentication changes to take effect
    if not using_systemd:
        cmd = [pg_ctl, '-D', pgsdata, 'restart'] # restart server
        result, msg = external_call(cmd, returnoutput=True, background=True)
        if (not result == "OK"):
            return "ERROR", msg

    else:
        cmd = ['sudo', 'systemctl', 'restart', 'wadpostgresql']
        result, msg = external_call(cmd, returnoutput=True)
        
    # check if postgres service is running
    result, msg = wait_pgready(pgport)
    if result == "ERROR":
        return "ERROR", msg

    return result, msg

def initialize_wadqc(wadroot=None):
    """
    initialize database
    """
    logger = logging.getLogger(LOGGERNAME)
    logger.info('Initializing database for WAD-QC...')

    result, msg = ("OK", "")
    try:
        from wad_qc.connection import dbio
        from peewee import ImproperlyConfigured
    except ImportError as e:
        result = "ERROR"
        msg = "Missing packages! {}".format(e)
        return result, msg
    
    if wadroot is None:
        wadroot = os.environ.get('WADROOT', None)
    if wadroot is None:
        msg = "Cannot initialize_wadqc without wadroot! {}".format(e)
        return result, msg

    inifile   = os.path.join(wadroot, 'WAD_QC', 'wadconfig.ini')
    setupfile = os.path.join(wadroot, 'WAD_QC', 'wadsetup.ini')

    try:
        dbio.db_create_only(inifile, setupfile)
    except Exception as e:
        result = "ERROR"
        msg = "Cannot initialize WAD-QC database! {}".format(e)
        return result, msg
    return result, msg


if __name__ == "__main__":
    do_create_postgresql_datadir = False
    do_create_databases = False
    do_initialize_wadqc = False
    pg_port = 5432
    
    installation_root = os.environ.get('WADROOT', None)

    # do not run as root! the script will ask for permission if it needs root
    if os.name == 'nt':
        pass
    elif os.geteuid() == 0:
        logger.error("Do not run wad_setup as root! The script will ask you for root permission if it needs it! Exit.")    
        exit(False)

    parser = argparse.ArgumentParser(description='Create WAD-QC Databases')
    parser.add_argument('--create_postgresql_datadir',
                        default=do_create_postgresql_datadir,action='store_true',
                        help='Create root PostgreSQL datadir [{}]'.format(do_create_postgresql_datadir),
                        dest='do_create_postgresql_datadir')
    parser.add_argument('--create_databases',
                        default=do_create_databases,action='store_true',
                        help='Create PostgreSQL databases for WAD-QC and Orthanc [{}]'.format(do_create_databases),
                        dest='do_create_databases')
    parser.add_argument('-r', '--root',
                        default=installation_root,
                        type=str,
                        help='root folder for WAD-QC and Orthanc [{}].'.format(installation_root),
                        dest='installation_root')
    parser.add_argument('-p', '--pg_port',
                        default=pg_port,
                        type=int,
                        help='port for PostgreSQL server [{}].'.format(pg_port),
                        dest='pg_port')

    parser.add_argument('--initialize_wadqc',
                        default=do_initialize_wadqc,action='store_true',
                        help='Initialize PostgreSQL database for WAD-QC [{}]'.format(do_initialize_wadqc),
                        dest='do_initialize_wadqc')

    args = parser.parse_args()
    if True not in [args.do_create_postgresql_datadir, args.do_create_databases, args.do_initialize_wadqc]:
        parser.print_help()
        exit(False)

    if args.installation_root is None:
        print('Error! --root is needed. Exit.\n\n')
        parser.print_help()
        exit(False)

    if args.do_create_postgresql_datadir:
        result, msg = create_postgresql_datadir(args.installation_root, args.pg_port)
        if result == "ERROR":
            print(result, msg)
            parser.print_help()
            exit(False)

    if args.do_create_databases:
        result, msg = create_databases(args.installation_root, args.pg_port)
        if result == "ERROR":
            print(result, msg+'\n\n')
            parser.print_help()
            exit(False)

    if args.do_initialize_wadqc:
        result, msg = initialize_wadqc(args.installation_root)
        if result == "ERROR":
            print(result, msg+'\n\n')
            parser.print_help()
            exit(False)


import os
import subprocess
import time
import logging
import sys
import errno

from . import helpers
from .defaults import LOGGERNAME
from .addtoenv import copy_wadqc_from_bash
from .distro import distro

EXIT_RESTART_SERVICES = 230
EXIT_DBUPGRADE_RESTART = 240

logger = logging.getLogger(LOGGERNAME)

def apt_install(pkgs, **kwargs):
    # replace python-dev and friends by python3-dev etc when running python3
    if sys.version_info >= (3, 0): # python3
        pkgs = [p.replace('python-', 'python3-') for p in pkgs]
    
    return helpers.apt_install(pkgs, **kwargs)

def yum_install(pkgs, **kwargs):
    # replace python-dev and friends by python3-dev etc when running python3
    if sys.version_info >= (3, 0): # python3
        pkgs = [p.replace('python-', 'python3-') for p in pkgs]
    
    return helpers.yum_install(pkgs, **kwargs)

def pip_upgrade_pip():
    return helpers.pip_upgrade_pip()

def pip_install(pkglist, **kwargs):
    return helpers.pip_install(pkglist, **kwargs)

def pip_install_requirements(**kwargs):
    return helpers.pip_install_requirements(**kwargs)

def create_folders_settings(**kwargs):
    """
    Create the WADQC Root folder, and all subfolders. Create settings files for WADQC services.
    """
    from . import folders_settings as fs

    result, msg = fs.create_folders(**kwargs)
    if result == "ERROR":
        return result, msg

    result, msg = fs.create_scripts('postgresql', **kwargs)
    if result == "ERROR":
        return result, msg

    return result, msg

def postgresql_install(source, **kwargs):
    """
    Install postgresql. Several options, depending on source
    """
    logger.info("Installing PostgreSQL ({})...".format(source))
    # check the requested port for postgresql
    pg_port = kwargs.get('pgsql_port', 5432)
    # not configurable for bigsql so use default port
    if source.startswith('bigsql'):
        pg_port = 5432
    if not helpers.port_available(pg_port):
        result = 'ERROR'
        msg = 'Requested postgresql port ({}) is not available!'.format(pg_port)
        return result, msg

    if source.startswith('bigsql'):
        """
        Install from BiqSQL
        """
        pgver = 'pg96'
        if source.endswith('95'):
            pgver = 'pg95'
        elif source.endswith('10'):
            pgver = 'pg10'
        elif source.endswith('11'):
            pgver = 'pg11'

        # bigsql scripts are fixed for python3, no need for kludges
        bigsqldir = os.path.join(kwargs['installation_root'], 'bigsql')
        from .addtoenv import addtoenv
        addtoenv({'PATH': os.path.join(bigsqldir,pgver,'bin')})

        cmd = ['python', '-c', '"$(curl -fsSL http://s3.amazonaws.com/pgcentral/install.py)"']
        result, msg = helpers.external_call(cmd, returnoutput=True, background=False, opt={'cwd': kwargs['installation_root'], 'shell': True})
        if result == 'ERROR':
            if 'SyntaxWarning: "is" with a literal' in msg:
                logger.warn('Ignoring message "{}"'.format(msg))
                result = 'OK'
            else:
                return result, msg
        elif 'ERROR' in msg: # ERROR: <urlopen error [Errno -3] Temporary failure in name resolution>
            return 'ERROR', msg

        # make sure we see the latests releases
        cmd = ['./pgc', 'update']
        result, msg = helpers.external_call(cmd, returnoutput=True, background=False, opt={'cwd': bigsqldir})
        if result == 'ERROR':
            return result, msg
        elif 'ERROR' in msg: # ERROR: <urlopen error [Errno -3] Temporary failure in name resolution>
            return 'ERROR', msg

        cmd = ['./pgc', 'install', pgver]
        result, msg = helpers.external_call(cmd, returnoutput=True, background=False, opt={'cwd': bigsqldir})
        if result == 'ERROR':
            return result, msg
        elif 'ERROR' in msg: # ERROR: <urlopen error [Errno -3] Temporary failure in name resolution>
            return 'ERROR', msg
        

    elif source == 'apt_systemd':
        # install postgresql from apt
        result, msg = helpers.apt_install(['postgresql'])
        if result == "ERROR":
            return result, msg
        
        import getpass
        user = getpass.getuser() # gets the name of the user running this shell

        # add wad user to the postgres group
        cmd = ['sudo', 'usermod', '-a', '-G', 'postgres', user] # add wad user to the postgres group
        result, msg = helpers.external_call(cmd)
        if result == "ERROR":
            return result, msg

        if pg_port == 5432:
            # disable systemd service
            cmds = [
                ['sudo', 'systemctl', 'stop', 'postgresql'],
                ['sudo', 'systemctl', 'disable', 'postgresql'], # no longer auto start
                ['sudo', 'systemctl', 'mask', 'postgresql'], # make it invisible
                ['sudo', 'chown', '-R', '{}:{}'.format(user,user), '/var/run/postgresql', '/var/log/postgresql'], # make sure wad user can write here initially
            ]
            for cmd in cmds:
                result, msg = helpers.external_call(cmd)
                if result == "ERROR":
                    return result, msg
            
    elif source == 'yum_systemd':
        # install postgresql from yum
        result, msg = helpers.yum_install(['postgresql-server'])
        if result == "ERROR":
            return result, msg
        
        import getpass
        user = getpass.getuser() # gets the name of the user running this shell

        if pg_port == 5432:
            # disable systemd service
            # --> service comes disabled upon install
            cmds = [
                ['sudo', 'usermod', '-a', '-G', 'postgres', user], # add wad user to the postgres group
                ['sudo', 'systemctl', 'mask', 'postgresql'], # make it invisible
                ['sudo', 'mkdir', '-p', '/var/log/postgresql'], # create log dir
                ['sudo', 'chown', '-R', '{}:{}'.format(user,user), '/var/run/postgresql', '/var/log/postgresql'], # make sure wad user can write here initially
            ]
            for cmd in cmds:
                result, msg = helpers.external_call(cmd)
                if result == "ERROR":
                    return result, msg
            
    else:
        raise ValueError('Unknown source {}'.format(source))
    return result, msg

def orthanc_install(source, **kwargs):
    if source.startswith('dropbox_'):
        if source.endswith('Lin64_Ubuntu1604'):
            #pkgurl = 'https://www.dropbox.com/s/a99subavuy79rpb/orthanc120fix_Lin64_Ubuntu1604.tar.gz?dl=1' #Orthanc 1.2.0 with dcmtk-3.6.0 time-out fix
            #pkgurl = 'https://www.dropbox.com/s/2dvcqpf2m4v83ot/orthanc130fix_Lin64_Ubuntu1604.tar.gz?dl=1' #Orthanc 1.3.0 with dcmtk-3.6.2 threads fix and PostgreSQL 9.6.1 with boost 1.64.0 fix
            pkgurl = 'https://www.dropbox.com/s/29aubuvoneeojmi/orthanc141fix_Lin64_Ubuntu1604.tar.gz?dl=1' #Orthanc 1.4.1 with PostgreSQL 2.2 with compile flags fixes
        elif source.endswith('Lin64_Ubuntu1610'):
            #pkgurl = 'https://www.dropbox.com/s/lsmd7z22pkghdzr/orthanc_Lin64_Ubunto1610.tar.gz?dl=1'
            pkgurl = 'https://www.dropbox.com/s/0k9l5cn8ftw4nup/orthanc120fix_Lin64_Ubuntu1610.tar.gz?dl=1' #Orthanc 1.2.0 with dcmtk-3.6.0 time-out fix
        elif source.endswith('Lin64_Ubuntu1704'):
            #pkgurl = 'https://www.dropbox.com/s/g6erzp46fw0c3ux/orthanc120fix_Lin64_Ubuntu1704.tar.gz?dl=1' #Orthanc 1.2.0 with dcmtk-3.6.0 time-out fix
            pkgurl = 'https://www.dropbox.com/s/5zkrxx6k2qqbl5x/orthanc130fix_Lin64_Ubuntu1704.tar.gz?dl=1' #Orthanc 1.3.0 with dcmtk-3.6.2 threads fix and PostgreSQL 9.6.1 with boost 1.64.0 fix
        elif source.endswith('Lin64_Ubuntu1710'):
            pkgurl = 'https://www.dropbox.com/s/mcwlef1udm7txea/orthanc130fix_Lin64_Ubuntu1710.tar.gz?dl=1' #Orthanc 1.3.0 with dcmtk-3.6.2 threads fix and PostgreSQL 9.6.1 with boost 1.64.0 fix
        elif source.endswith('Lin64_Ubuntu1804'):
            pkgurl = 'https://www.dropbox.com/s/6vee713qg58ju0a/orthanc141fix_Lin64_Ubuntu1804.tar.gz?dl=1' #Orthanc 1.4.1 with PostgreSQL 2.2 with compile flags fixes
        elif source.endswith('Lin64_CentOS7'):
            pkgurl = 'https://www.dropbox.com/s/ssdqnyce3ien7d6/orthanc130_Lin64_CentOS7.tar.gz?dl=1' #Orthanc 1.3.0
        else:
            raise ValueError('Unknown version {}'.format(source))
        
        dstfolder = kwargs['installation_root']
        from .addtoenv import addtoenv
        addtoenv({'PATH': os.path.join(dstfolder, 'orthanc', 'bin')})

        result,msg = helpers.unpack_from_url(pkgurl, dstfolder, remove_old=False)
        if result == 'ERROR':
            return result, msg

        
    elif source == 'apt_systemd':
        # install orthanc from apt
        pkgs = ['orthanc']

        # find out if repo has 'orthanc-postgresql'
        psq_pkg = 'orthanc-postgresql'
        cmd = ['apt-cache', 'search', psq_pkg]
        result, msg = helpers.external_call(cmd, returnoutput=True)
        if msg.strip().startswith(psq_pkg):
            pkgs.append(psq_pkg)

        result, msg = helpers.apt_install(pkgs)
        if result == "ERROR":
            return result, msg
        
        # disable systemd service
        cmds = [
            ['sudo', 'systemctl', 'stop', 'orthanc'],
            ['sudo', 'systemctl', 'disable', 'orthanc'], # no longer auto start
            ['sudo', 'systemctl', 'mask', 'orthanc'], # make it invisible
        ]
        for cmd in cmds:
            result, msg = helpers.external_call(cmd)
            if result == "ERROR":
                return result, msg
            
    else:
        raise ValueError('Unknown source {}'.format(source))

    return result, msg


def create_postgresql_datadir(installation_root, **kwargs):
    """
    If PostgreSQL is installed from a standard repository (Ubuntu apt-get) this step is not needed.
    When BigSQL is used, a root PostgreSQL datadir is not created automatically, and this step is
    needed before create_databases databases can be called.
    
    create_folders_settings must have been run first
    """
    from . import database_setup as ds
    pgport = kwargs.get('pgsql_port', 5432)
    result, msg = ds.create_postgresql_datadir(installation_root, pgport) # create_folders_settings must have been run first

    return result, msg
    
def create_databases(installation_root, **kwargs):
    """
    If PostgreSQL is installed from a standard repository (Ubuntu apt-get) this step is not needed.
    When BigSQL is used, a root PostgreSQL datadir is not created automatically, and this step is
    needed before create_databases databases can be called.
    
    create_folders_settings must have been run first
    """
    from . import database_setup as ds
    pgport = kwargs.get('pgsql_port', 5432)
    result, msg = ds.create_databases(installation_root, pgport) # create_folders_settings must have been run first

    return result, msg
    

def initialize_wadqc(installation_root, **kwargs):
    """
    initialize database
    
    create_folders_settings must have been run first
    """
    from . import database_setup as ds
    result, msg = ds.initialize_wadqc(installation_root) # create_folders_settings must have been run first

    return result, msg

def enable_apache2(mode, **kwargs):
    """
    Setup apache2 for given init mode; right now only systemd
    """
    from . import apache2_setup as act
    result, msg = ("OK", "")

    result, msg = act.enable_apache2(mode, **kwargs)

    return result, msg

def enable_httpd(mode, **kwargs):
    """
    Setup apache2/httpd for given init mode; right now only systemd
    """
    from . import apache2_setup as act
    result, msg = ("OK", "")

    result, msg = act.enable_httpd(mode, **kwargs)

    return result, msg

def apache2_deploy_sites(sitelist, portlist, installation_root, **kwargs):
    """
    Deploy sitelist on apache2. Make sure apache2 is enabled before running this action
    """
    from . import apache2_setup as act
    result, msg = ("OK", "")

    result, msg = act.apache2_deploy_sites(sitelist, portlist, installation_root, **kwargs)

    return result, msg

def httpd_deploy_sites(sitelist, portlist, installation_root, **kwargs):
    """
    Deploy sitelist on httpd. Make sure httpd is enabled before running this action
    """
    from . import apache2_setup as act
    result, msg = ("OK", "")

    result, msg = act.httpd_deploy_sites(sitelist, portlist, installation_root, **kwargs)

    return result, msg

def enable_nginx(mode, **kwargs):
    """
    Setup nginx for given init mode; right now only systemd
    """
    from . import nginx_setup as act
    result, msg = ("OK", "")

    result, msg = act.enable_nginx(mode, **kwargs)

    return result, msg

def nginx_deploy_sites(sitelist, portlist, installation_root, **kwargs):
    """
    Deploy sitelist on nginx. Make sure nginx is enabled before running this action
    """
    from . import nginx_setup as act
    result, msg = ("OK", "")

    result, msg = act.nginx_deploy_sites(sitelist, portlist, installation_root, **kwargs)

    return result, msg

def firewall_add_port(portlist, **kwargs):
    """
    Open ports in firewall
    """
    from . import apache2_setup as act
    result, msg = ("OK", "")

    result, msg = act.firewall_add_port(portlist, **kwargs)

    return result, msg

def create_start_systemd(service, installation_root, **kwargs):
    """
    Create a systemd startup script for given service, and startup now
    """
    from . import systemd_setup as act
    result, msg = ("OK", "")

    result, msg = act.create_start_systemd(service, installation_root, **kwargs)

    return result, msg

def create_virtualenv(name, workon_home, python3, activate_on_login, **kwargs):
    """
    Install requirements for virtualenv, create Envs home, make an environment named <name> of python3 (True)
    """
    from .addtoenv import addtoenv, addtobash, removefrombash
    from .which import which
    result, msg = ("OK", "")

    # cannot run this script from within a virtualenv
    if 'VIRTUAL_ENV' in os.environ:
        result = "ERROR"
        msg = "Cannot create a virtualenv from within a virtualenv. Run this script outside a virtualenv (deactivate first)"
        return result, msg
    
    # pip install packages
    # at least centos7 has a problem with installing virtualenvwrapper==4.8.4
    result, msg = helpers.pip_install(['virtualenv', 'virtualenvwrapper==4.8.2', 'wheel', 'setuptools'])
    if not result == "OK":
        if "Python 2.7 will reach the end" in msg or "Python 2.7 reached the end" in msg:
            result = "OK"
        else:
            return result, msg
        
    # add .local/bin to PATH if not already added
    if not '.local/bin' in os.environ['PATH']:
        addtoenv({'PATH': os.path.expanduser('~/.local/bin')})

    dist = distro()

    # setup virtualenv stuff
    workon_home = os.path.abspath(os.path.expanduser(workon_home))
    addtoenv({'WORKON_HOME': workon_home})

    if which('python') is None: # fix for installations with only python3
        addtoenv({'VIRTUALENVWRAPPER_PYTHON': which('python3')})
             
    line = 'source $HOME/.local/bin/virtualenvwrapper.sh'

    if activate_on_login:
        line = '{}\nworkon {}'.format(line, name)
    else:
        removefrombash('workon {}'.format(name))
    addtobash(line)
        
    if python3:
        pyexe = which('python3')
        if pyexe is None:
            result = "ERROR"
            msg = "Python3 not installed. Attempting to install system python3 package"
            logger.warning(msg)
            if 'centos' in dist['distro'] or 'redhat' in dist['distro']:
                result, msg = yum_install(['python36', 'python36-pip'])
            else:
                result, msg = apt_install(['python3'])
            if result == "ERROR":
                return result, msg
            if 'centos' in dist['distro'] or 'redhat' in dist['distro']:
                # python 34 is depreciated, so go to python36
                # however, python36 is not symlinked to python3
                # so make that link
                pyexe = which('python3')
                if pyexe is None:
                    msg = "Linking python36 to python3"
                    logger.info(msg)
                    cmds = [ 
                        ['sudo', 'rm', '-f', '/usr/bin/python3'],
                        ['sudo', 'ln', '-s', '/usr/bin/python36', '/usr/bin/python3']
                    ]
                    for cmd in cmds:
                        result, msg = helpers.external_call(cmd)
                        if result == "ERROR":
                            return result, msg

                pipexe = which('pip3.6')
                if pipexe is None:
                    msg = "Linking pip3.6 to pip3"
                    logger.info(msg)
                    cmds = [ 
                        ['sudo', 'rm', '-f', '/usr/bin/pip3', '/usr/bin/pip3.6'],
                        ['sudo', 'ln', '-s', '/usr/local/bin/pip3.6', '/usr/bin/pip3'],
                        ['sudo', 'ln', '-s', '/usr/local/bin/pip3.6', '/usr/bin/pip3.6']
                    ]
                    for cmd in cmds:
                        result, msg = helpers.external_call(cmd)
                        if result == "ERROR":
                            return result, msg

            pyexe = which('python3')
            if pyexe is None:
                result = "ERROR"
                msg = "Python3 not installed. Attempting to install system python3 package failed!"
                logger.error(msg)
                return result, msg
    else:
        pyexe = which('python')

    # execute make a virtualenv
    try:
        os.makedirs(kwargs['installation_root'])
    except OSError as e: 
        if e.errno == errno.EEXIST and os.path.isdir(kwargs['installation_root']):
            pass
        else:
            result = 'ERROR'
            msg = str(e)

    # just make it easier and execute a bash
    dest = os.path.join(kwargs['installation_root'], "mkv.sh")
    
    with open(dest, 'w') as f:
        if which('python') is None: # fix for installations with only python3
            f.write('export VIRTUALENVWRAPPER_PYTHON={}\n'.format(which('python3')))
        f.write('export PATH=$HOME/.local/bin:$PATH\n')
        f.write('source $HOME/.local/bin/virtualenvwrapper.sh\n')
        f.write('mkvirtualenv {} --python={}'.format(name, pyexe))

    bexe = which('bash') # must be bash for 'source' to work!
    result, msg = helpers.external_call([bexe, dest], returnoutput=True)
    os.remove(dest)

    if "virtualenvwrapper.user_scripts creating" in msg:
        result = 'OK'
        logger.info('{}'.format(msg))
    
    return result, msg

def clean_permissions_wadroot(installation_root, using_nginx):
    """
    For security, remove permissions of group/others
    """
    result, msg = ("OK", "")

    result, msg = helpers.clean_permissions_wadroot(installation_root, using_nginx)
    return result, msg

def check_selinux_status():
    """
    Check SE-Linux status (only on CentOS / RedHat systems)
    WADQC needs SE-Linux disabled because postgresql and httpd sites are run
    as regular user. Maybe it is possible to get this working with SE-Linux
    enabled in a future release.
    """
    result, msg = ("OK", "")

    cmd = ['sestatus']
    result, msg = helpers.external_call(cmd, returnoutput=True, background=False)
    if result == 'ERROR':
        return result, msg
    # convert to dict to check individual items and check these
    try:
        logger.info("sestatus report\n{}".format(msg))
        msgdict = dict(x.split(':') for x in msg.split('\n'))
        result, msg = ("OK", "")
        # disabled or permissive are okay
        if 'enabled' in msgdict['SELinux status']:
            # enabled, need further checks
            currentModeEnforced = 'enforcing' in msgdict['Current mode']
            configFileEnforced = 'enforcing' in msgdict['Mode from config file']
            if currentModeEnforced or configFileEnforced:
                # not ok
                result = 'ERROR'
                msg = 'SE-Linux is enabled. WAD-QC software needs SE-Linux permanently disabled.'
                if currentModeEnforced:
                    # currently not disabled
                    msg = msg + '\nDisable SE-Linux until next reboot with:'
                    msg = msg + '\n  sudo setenforce 0'
                if configFileEnforced:
                    # not permanently disabled
                    msg = msg + '\nTo disable SE-Linux permanently, edit /etc/selinux/config'
                    msg = msg + '\nand change SELINUX=enforcing to SELINUX=disabled'
                    msg = msg + '\nOpen a minmal editor with:'
                    msg = msg + '\n  sudo nano /etc/selinux/config'
                else:
                    # permanently disabled but currently enabled may also be solved with reboot
                    msg = msg + '\nOr reboot now.'
                msg = msg + '\n'
            else:
                # ok to continue
                logger.info('SE-Linux is currently disabled and configured disabled or permissive on next reboot.')
            
    except Exception as e:
        # failed to interpret...
        result, msg = ("ERROR", "Something went wrong while interpreting output from sestatus command.\n {}".format(str(e)))
    
    return result, msg

def platform_fixes(fixes, **kwargs):
    # apply some platform specific patches
    return helpers.platform_fixes(fixes, **kwargs)
    
def replace_systemd(**kwargs):
    # replace systemctl with a python wrapper for systems that do not fully support systemd
    from . import systemd_setup as act

    result, msg = ("OK", "")

    result, msg = act.replace_systemd(**kwargs)

    return result, msg

def wadservices(**kwargs):
    # exit with a given status so that wad_setup.sh can execute the given command
    logger.info("Requesting automatically restarting of wadservices...")
    cmd = kwargs.get('command', None)
    services = kwargs.get('services', None)
    if cmd == 'restart' and services == 'all':
        venvpath = kwargs.get('virtualenv', None)
        venvname = None
        if not venvpath is None:
            venvname = os.path.basename(os.path.dirname(venvpath))
        copy_wadqc_from_bash(".venvsetup", venvname)
        logging.shutdown()
        exit(EXIT_RESTART_SERVICES)
        
    result, msg = ("ERROR", "command '{}' with services '{}' not implemented".format(str(cmd), str(services)))
    return result, msg
    
def dbupgrade(**kwargs):
    # run all available dbupgrades
    logger.info("Requesting automatically upgrade of dbwadqc and restarting of wadservices...")
    venvpath = kwargs.get('virtualenv', None)
    venvname = None
    if not venvpath is None:
        venvname = os.path.basename(os.path.dirname(venvpath))
    copy_wadqc_from_bash(".venvsetup", venvname)
    logging.shutdown()
    exit(EXIT_DBUPGRADE_RESTART)
    
def restrict_privileges(**kwargs):
    # remove unneeded priviliges of installing user
    logger = logging.getLogger(LOGGERNAME)

    logger.info("Restricting priviliges of installing user...")
    return helpers.restrict_privileges(**kwargs)

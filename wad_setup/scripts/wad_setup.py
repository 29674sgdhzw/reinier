#!/usr/bin/env python
from __future__ import print_function
# -*- coding: iso-8859-1 -*-

__version__ = '20200429'

"""
Workflow:
 1. read json file with instructions
 2. do it!

Changelog:
  20200429: support for python3.8 (remove platform.dist())
  20200306: forget about --no-site-packages (has been a dummy parameter since before WAD-QC2)
  20200305: deal with present python2 deprecation; fix for debian10
  20190209: deal with future python2 deprecation
  20190206: start supporting debian
  20180926: merged 20180925 and 20180919
  20180925: moved setup.py to scripts folder
  20180919: Added CentOS7 compatibility
  20180807: catch "amazon Temporary failure in name resolution"
  20180803: wait out dpkg lock; more logging
  20180710: Missed some errors in actions; changes for docker; fix broken python36x; added support for multiple postgresql clusters
  20180706: Replace deprecated imp. move wad_setup.py and actions.py to scripts folder. errno no longer in os. 
            install python3-pip when running python3
  20180629: Added pip install -r requirements for base system
  20180209: Added virtualenv fix for systems with only python3 installed
  20170921: Added setuptools as requirements
  20170503: Added custom ports for PostgreSQL and Orthanc.
  20170418: Fixes for Windows
  20170314: New links for timeout fixed precompiled Orthanc; only store headers in Orthanc PostgreSQL (raw data on filesystem);
            added QR for WADQC; changed default name
  20170221: Move initial dependencies inside main
  20170209: Initial version
"""
import os
import sys
import argparse
import logging

# pretend this script is still in wad_setup instead of wad_setup/scripts
sys.path.append(os.getcwd())

from scripts import actions
from scripts.distro import distro
from scripts.defaults import LOGGERNAME
from scripts.logger import setup_logging
from scripts.addtoenv import addtoenv, copy_wadqc_from_bash

EXIT_RESTART_SETUP = 210

def _exit(success):
    # shutdown logging, closing all file handles and flushing all output
    logging.shutdown()
    exit(success)

def check_install_pip():
    # check if pip is installed. If not, install it now.
    logger = logging.getLogger(LOGGERNAME)

    try:
        import pip
    except ImportError:
        logger.info("Installing pip:...")
        pkg = 'python-pip'
        if sys.version_info >= (3, 0): # python3
            pkg = 'python3-pip'

        dist = distro()
        if 'centos' in dist['distro'] or 'redhat' in dist['distro']:
            # CentOS7
            if sys.version_info.major == 3 and sys.version_info.minor == 6: # python36
                pkg = 'python36-pip'

            result, msg = actions.yum_install([pkg]) # this works only on Redhat/CentOS systems
            if "Importing GPG key" in msg:
                result = "OK"
            if result == "ERROR":
                logger.error("{}: {}".format(result, msg))
                exit(False)
            logger.info("{}".format(result))
            
            # check if pip needs to upgrade itself
            logger.info("{}".format("Checking if pip needs to upgrade itself..."))
            result, msg = actions.pip_upgrade_pip()
            if result == "ERROR":
                if "Python 2.7 will reach the end" in msg or "Python 2.7 reached the end" in msg:
                    result = "OK"
                else:
                    logger.error("{}: {}".format(result, msg))
                    exit(False)
            logger.info("{}".format(result))
        else:
            # Ubuntu
            result, msg = actions.apt_install([pkg]) # this works only on debian/ubuntu systems

def check_install_modules():
    # check if required modules for this installer are installed. If not, do install them.
    logger = logging.getLogger(LOGGERNAME)

    try:
        import jsmin
        import simplejson as json
        import requests
    except ImportError:
        reqs = ['setuptools', 'jsmin', 'simplejson', 'requests']
        logger.info("Installing packages ({}):...".format(', '.join(reqs)))
        result, msg = actions.pip_install(reqs)
        if result == "ERROR":
            if "Python 2.7 will reach the end" in msg or "Python 2.7 reached the end" in msg:
                result = "OK"
            else:
                logger.error("{}: {}".format(result, msg))
                exit(False)
        logger.info("{}".format(result))

        """
        Make sure the newly installed modules can be imported
        The proper way is to do:
        # rescan path to pick up new modules
        import site
        try:
            reload(site)
        except NameError as e: # moved to importlib in python3
            from importlib import reload
            try:
                reload(site)
            except TypeError as e: # try to fix broken python 3.6.x
                fix_python36x(site)
    
        but this is broken for python 3.6.x. It can be fixed by overriding site.abs_paths(),
        but a simpler fix is just adding the folder $HOME.local/lib/python3.6/site-packages
        """
        import site
        if site.ENABLE_USER_SITE: # not for virtualenv
            logger.info("Making the just installed packages importable...")
            user_site = site.getusersitepackages()
            if not user_site in sys.path:
                sys.path.append(user_site)

def check_create_virtualenv(venvpath, **kwargs):
    # <venv_home>/<venv_name>/bin
    if not os.path.basename(venvpath) == 'bin':
        logger.error('virtualenv parameter should be of the form <venv_home>/<venv_name>/bin')
        _exit(False)
    venvname = os.path.basename(os.path.dirname(venvpath))
    venvhome = os.path.dirname(os.path.dirname(venvpath))
    if not os.path.exists(venvpath):
        logger.info("Creating a new virtualenv...")
        result, msg = actions.create_virtualenv(venvname, venvhome, python3=True, activate_on_login=False, **kwargs)
        if result == "ERROR":
            if "Python 2.7 will reach the end" in msg or "Python 2.7 reached the end" in msg:
                result = "OK"
            else:
                logger.error("{}: {}".format(result, msg))
                exit(False)
        logger.info("{}, {}".format(result, msg))
        logger.info("Done.")
        logger.info("If wad_setup does not continue automatically, exit this shell, start a new one and execute\n  workon {}\nThen run wad_setup again to finish installation".format(venvname))
        copy_wadqc_from_bash(".venvsetup", venvname)
        logger.info("Requesting automatic continuation of wad_setup in just created virtualenv '{}'...".format(venvname))
        exit(EXIT_RESTART_SETUP)
    
    if 'VIRTUAL_ENV' in os.environ and not os.environ['VIRTUAL_ENV'] == os.path.dirname(venvpath):
        logger.error('Current virtualenv is {} but requested one is {}. \nExecute\n  workon {}\nand try again.'.format(os.path.basename(os.environ['VIRTUAL_ENV']), venvname, venvname))
        _exit(False)
    
    if not 'VIRTUAL_ENV' in os.environ:
        logger.error('Not running in requested virtualenv {}. \nExecute\n  workon {}\nand try again.'.format(venvname, venvname))
        _exit(False)
    
def check_install_platform_pkgs():
    """
    a central place to install packages specific for a linux distribution
    """
    logger = logging.getLogger(LOGGERNAME)

    dist = distro()
    if 'centos' in dist['distro'] or 'redhat' in dist['distro']:
        # CentOS7
        logger.info("Check if SE-Linux is disabled:...")
        result, msg = actions.check_selinux_status()
        if result == "ERROR":
            logger.error("{}: {}".format(result, msg))
            exit(False)
        logger.info("{}".format(result))
        
        logger.info("Installing EPEL repository: package epel-release:...")
        result, msg = actions.yum_install(['epel-release']) # this works only on Redhat/CentOS systems
        if result == "ERROR":
            logger.error("{}: {}".format(result, msg))
            exit(False)
        logger.info("{}".format(result))
        
        pkgs = ['which', 'gcc']
        logger.info("Installing required packages: {}".format(', '.join(pkgs)))
        result, msg = actions.yum_install(pkgs) # this works only on Redhat/CentOS systems
        if "Importing GPG key" in msg:
            result = "OK"
        if result == "ERROR":
            logger.error("{}: {}".format(result, msg))
            exit(False)
        logger.info("{}".format(result))
    elif 'debian' in dist['distro']:
        # need to add /usr/sbin to PATH for Orthanc, a2tools
        addtoenv({'PATH': '/usr/sbin'})

        # needed for debian10; not needed for debian9
        if not (dist['version'].startswith('9.') or dist['version'] == '9'):
            pkgs = ['python3-distutils']
            logger.info("Installing required packages: {}".format(', '.join(pkgs)))
            result, msg = actions.apt_install(pkgs) # this works only on debian/ubuntu systems
            if result == "ERROR":
                logger.error("{}: {}".format(result, msg))
                exit(False)
            logger.info("{}".format(result))

        # need to switch to root, install sudo, add waduser to sudo group, login/logout
        
    
if __name__ == "__main__":
    # do not run as root! the script will ask for permission if it needs root
    if os.name == 'nt':
        pass
    elif os.geteuid() == 0:
        print("Do not run wad_setup as root! The script will ask you for root permission if it needs it! Exit.")    
        exit(False)

    # setup as soon as possible
    setup_logging('INFO', LOGGERNAME, logfile_only=False)

    # check special requirements fo this platform
    check_install_platform_pkgs()
    
    # check if pip is installed, if not, install it through apt:
    check_install_pip()
    
    # check if packages for this setup script are available
    check_install_modules()

    # import (new) modules
    import jsmin
    import simplejson as json
    import requests
    
    logger = logging.getLogger(LOGGERNAME)
    recipefile = 'recipes/dummy.json'#None
    parser = argparse.ArgumentParser(description='WAD Setup')
    parser.add_argument('-r','--recipe',
                        default=recipefile,
                        type=str,
                        help='the json file with setup instructions [{}].'.format(recipefile),
                        dest='recipefile')

    args = parser.parse_args()
    if args.recipefile is None or args.recipefile == recipefile:
        parser.print_help()
        _exit(False)

    # sanity checks 
    if not os.path.exists(args.recipefile):
        logger.error('Setup file "{}" does not exist. Exit.'.format(args.recipefile))
        _exit(False)
    try:
        with open(args.recipefile) as f:
            validjson = jsmin.jsmin(f.read()) # strip comments and stuff from more readable json
        setup = json.loads(validjson)

    except Exception as e:
        logger.error('Setup file "{}" is not a valid json file. {}, Exit.'.format(args.recipefile, str(e)))
        _exit(False)

    if 'installation_root' in setup['global_params']: # does not have to exist e.g. for upgrade script
        setup['global_params']['installation_root'] = os.path.abspath(
            os.path.expanduser(setup['global_params']['installation_root']))
    setup['global_params']['__recipe_path'] = os.path.abspath(
        os.path.expanduser(args.recipefile))
    setup['global_params']['__setup_folder'] = os.path.abspath(
        os.path.expanduser(os.path.dirname(os.path.realpath(__file__))))

    # make sure the given virtualenv exists
    venvpath = None
    if 'virtualenv' in setup['global_params'] and not setup['global_params']['virtualenv'].strip() == "":
        venvpath = os.path.abspath(
            os.path.expanduser(setup['global_params']['virtualenv']))
        setup['global_params']['virtualenv'] = venvpath
        check_create_virtualenv(venvpath, **setup['global_params'])

    if 'installation_root' in setup['global_params']: # does not have to exist e.g. for upgrade script
        # need to set installation_root as WADROOT now! Every script needs it!
        result2, msg2 = addtoenv( {'WADROOT':setup['global_params']['installation_root']} )

    logger.info('== Starting WAD Setup with recipe {} on platform {} =='.format(args.recipefile, distro()['name']))
    errors = 0
    advice_reboot = False
    using_nginx = False
    for act in setup['actions']:
        if not hasattr(actions, act['cmd']):
            logger.error('Unknown command "{}". Skipping.'.format(act['cmd']))
            continue
        for k,v in setup['global_params'].items():
            if not k in act['kwargs'].keys():
                act['kwargs'][k] = v
        result, msg = getattr(actions, act['cmd'])(**act['kwargs'])
        logger.info('{}: {}. {}'.format(act['cmd'], result, msg)) if result == 'OK' else logger.error('{}: {}. {}'.format(act['cmd'], result, msg))
        if not result == "OK": 
            logger.error('Error: {}'.format(msg))
            errors += 1
            break
        if act['cmd'] == 'platform_fixes':
            if 'fixes' in act['kwargs'].keys():
                if 'removeipc' in act['kwargs']['fixes']:
                    advice_reboot = True
        if act['cmd'] in ['enable_nginx', 'nginx_deploy_sites']:
            using_nginx = True

    # last step: remove group/other permissions from important files and folders
    if errors == 0:
        if 'installation_root' in setup['global_params']: # does not have to exist e.g. for upgrade script
            wadrootfolders = [setup['global_params']['installation_root']]
            if not venvpath is None:
                wadrootfolders.append(os.path.dirname(venvpath))
            result, msg = actions.clean_permissions_wadroot(wadrootfolders, using_nginx=using_nginx)
            logger.info(msg)

    if errors>0:
        logger.info('== {} Errors for WAD Setup with recipe {} =='.format(errors, args.recipefile))
        logger.info('Inspect {} for ERRORs. Rerun this recipe after fixing the ERRORS or close this shell and open a new one for the environment changes to take effect.'.format(LOGGERNAME))
    else:
        logger.info('== Successfully finished WAD Setup with recipe {} =='.format(args.recipefile))
        if venvpath is None:
            logger.info('Close this shell and open a new one for the environment changes to take effect. In the new shell manually (re)start all WAD-QC services:')
            logger.info('  wadservices -c restart')
        else:
            logger.info('Close this shell and open a new one for the environment changes to take effect. In the new shell activate the virtualenv and manually (re)start all WAD-QC services:')
            venvname = os.path.basename(os.path.dirname(venvpath))
            logger.info('  workon {}\n  wadservices -c restart'.format(venvname))
        if advice_reboot:
            logger.info('The installer has changed some system settings that require a system reboot to take effect.')
        logger.info('If you just upgraded an existing WAD-QC installation, manually restart all WAD-QC services: wadservices -c restart')
    _exit(True)


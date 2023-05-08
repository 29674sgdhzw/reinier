import os
import sys
import logging
from .helpers import external_call, apt_install, yum_install
from .folders_settings import copy_replaces
from .which import which
from .defaults import LOGGERNAME
from .actions import pip_install

logger = logging.getLogger(LOGGERNAME)

"""
Output files for running flask websites in apache2
Will need sudo.
"""

def enable_apache2(mode, **kwargs):
    """
    Apache2 is not enabled by default
    """
    logger.info('Enabling apache2...')
    result,msg = ("OK","")
    
    #1. install apache2 and mods
    if sys.version_info >= (3, 0): # python3
        mod = 'libapache2-mod-wsgi-py3'
    else:
        mod = 'libapache2-mod-wsgi'

    result,msg = apt_install(['apache2', mod])

    if result == "ERROR":
        return result, msg

    #2. enable dormant apache2
    if mode == 'systemd': # default for Ubuntu 16.04 and later
        cmds = [
            ['sudo', 'systemctl', 'enable', 'apache2'],
            ['sudo', 'systemctl', 'start', 'apache2'],
        ]
    else:
        result = "ERROR"
        msg = "Only systemd is implemented right now!"
        return result, msg

    for cmd in cmds:
        result, msg = external_call(cmd, returnoutput=True, background=False)
        mustquit = (not result == "OK")
        if mustquit:
            if 'apache2.service is not a native service' in msg or 'Synchronizing state of apache2.service' in msg:
                result = "OK"
            else:
                errormsg = 'ERROR! Could not enable apache2 for {}! '.format(mode)
                return result, errormsg+msg
    
    return result, msg

def enable_httpd(mode, **kwargs):
    """
    Apache2 is httpd on CentOS 7
    httpd is not enabled by default
    """
    logger.info('Enabling httpd...')

    from .helpers import pip_upgrade_pip
    
    result,msg = ("OK","")
    
   #1. install httpd / apache2 and mods
    # TODO: this is now very CentOS 7 specific...
    # yum package mod_wsgi works for python2 but not for python3
    if sys.version_info.major == 3 and sys.version_info.minor == 6: # python36
        #  need httpd-devel for pip install mod_wsgi to work
        result,msg = yum_install(['httpd', 'httpd-devel'])
        if result == "ERROR":
            return result, msg
        pip_upgrade_pip()

        # full path to pip3.6 is needed, because /usr/local/bin is not in the root's path
        # else virtualenv is tried but that fails
        #result, msg = pip_install(['mod-wsgi'])
        cmd = ['sudo', '/usr/local/bin/pip3.6', 'install', 'mod-wsgi'] 
        result, msg = external_call(cmd, returnoutput=True, background=False)
        if 'o such file or directory' in msg or 'ommand not found' in msg:
            cmd = ['sudo', '/usr/bin/pip3.6', 'install', 'mod-wsgi'] 
            result, msg = external_call(cmd, returnoutput=True, background=False)
        if result == "ERROR":
            if "You are using pip version":
                result = "OK"
            else:
                return result, msg
        
        # mod_wsgi-express install-module > /etc/httpd/conf.modules.d/02-wsgi.conf
        # first get stdout of command
        cmd = ['sudo', which('mod_wsgi-express'), 'install-module']
        result, msg = external_call(cmd, returnoutput=True, background=False)
        if result == "ERROR":
            return result, msg
        # now pipe msg to /etc/httpd/conf.modules.d/02-wsgi.conf
        dest = '/etc/httpd/conf.modules.d/02-wsgi.conf'
        tmpdest = '/tmp/02-wsgi.conf'
        with open(tmpdest, mode='w') as f:
            f.write(msg)
        cmd = ['sudo', 'mv', tmpdest, dest]
        result, msg = external_call(cmd, returnoutput=True, background=False)
        if result == "ERROR":
            return result, msg
            
    else:
        # this should work if system package mod_wsgi works with python3
        #mod = 'mod_wsgi'
        #result,msg = yum_install(['httpd', mod])
        # other python versions, not tested, may not work...
        result = "ERROR"
        msg = "Installer script for httpd on CentOS 7 or Redhat 7 only supports Python3.6"
        if result == "ERROR":
            return result, msg

    #2. enable dormant apache2 / httpd
    if mode == 'systemd': # default for CentOS7
        cmds = [
            ['sudo', 'systemctl', 'enable', 'httpd'],
            ['sudo', 'systemctl', 'start', 'httpd'],
        ]
    else:
        result = "ERROR"
        msg = "Only systemd is implemented right now!"
        return result, msg

    for cmd in cmds:
        result, msg = external_call(cmd, returnoutput=True, background=False)
        mustquit = (not result == "OK")
        if mustquit:
            if 'httpd.service is not a native service' in msg:
                result = "OK"
            if 'Created symlink from' in msg:
                result = "OK"
            else:
                errormsg = 'ERROR! Could not enable httpd (apache2) for {}! '.format(mode)
                return result, errormsg+msg
    
    return result, msg

def _deploy_sites(paths, sitelist, portlist, installation_root, **kwargs):
    """
    helper function generating the commands to copy the wsgi and conf scripts of sites
    http://flask.pocoo.org/docs/0.12/deploying/mod_wsgi/
    """
    nolisten = kwargs.get("nolisten", [])

    logger.info('...Deploying sites {}...nolisten: {}'.format(', '.join(sitelist), nolisten))

    import getpass
    user = getpass.getuser() # gets the name of the user running this shell

    if not "virtualenv" in kwargs.keys() or kwargs['virtualenv'].strip() == "": 
        venvbin = 'None' #Needs to be a string for replace!
    else:
        venvbin = '"{}"'.format(os.path.abspath(os.path.expanduser(kwargs['virtualenv']))) # note the quotes!

    # add the sites
    pos = { k:i for i,k in enumerate(sitelist)}
    cmds = []

    if 'wad_admin' in sitelist:
        # create proper paths in wsgi
        xtra_paths = [ os.path.dirname(p) for p in [which('wadcontrol'), which('Orthanc'), which('pg_config')]]
        dest = os.path.join(installation_root, 'admin_wadqc.wsgi')
        inlist  = ['__WADROOT__',   '__XTRAPATHS__', '__VENVBIN__', '\\']
        outlist = [installation_root, str(xtra_paths),    venvbin,       '/']
        copy_replaces(src=os.path.join(paths['wsgi'], 'admin_wadqc.wsgi'), 
                      dest=dest, 
                      inlist=inlist, 
                      outlist=outlist) 
        cmds.append(['sudo', 'cp', dest, os.path.join(paths['var'], os.path.basename(dest))])
        cmds.append(['rm', '-f', dest])

        # create proper paths in conf
        dest = os.path.join(installation_root, 'admin_wadqc.conf')

        # the multi-listen bug pops up is a port is defined in ports.conf and in Listen
        port = int(portlist[pos['wad_admin']])
        if port in nolisten:
            listen = "#Listen"
        else:
            listen = "Listen"

        inlist  = ['__LISTEN__',  '__USER__',   '__GROUP__', '__PORT__',  '\\']
        outlist = [listen,       user,          user,       str(port),  '/']
        copy_replaces(src=os.path.join(paths['conf'], 'admin_wadqc.conf'), 
                      dest=dest, 
                      inlist=inlist, 
                      outlist=outlist) 
        cmds.append(['sudo', 'cp', dest, os.path.join(paths['etc'], os.path.basename(dest))])
        cmds.append(['rm', '-f', dest])

        cmds.append(['sudo', paths['a2ensite'], 'admin_wadqc'])
        
    if 'wad_dashboard' in sitelist:
        # create proper paths in wsgi
        dest = os.path.join(installation_root, 'dashboard_wadqc.wsgi')
        inlist  = ['__WADROOT__',   '__VENVBIN__', '\\']
        outlist = [installation_root, venvbin,     '/']
        copy_replaces(src=os.path.join(paths['wsgi'], 'dashboard_wadqc.wsgi'), 
                      dest=dest, 
                      inlist=inlist, 
                      outlist=outlist) 
        cmds.append(['sudo', 'cp', dest, os.path.join(paths['var'], os.path.basename(dest))])
        cmds.append(['rm', '-f', dest])

        # create proper paths in conf
        dest = os.path.join(installation_root, 'dashboard_wadqc.conf')

        # the multi-listen bug pops up is a port is defined in ports.conf and in Listen
        port = int(portlist[pos['wad_dashboard']])
        if port in nolisten:
            listen = "#Listen"
        else:
            listen = "Listen"

        inlist  = ['__LISTEN__',  '__USER__',   '__GROUP__', '__PORT__',  '\\']
        outlist = [listen,       user,          user,       str(port),  '/']
        copy_replaces(src=os.path.join(paths['conf'], 'dashboard_wadqc.conf'), 
                      dest=dest, 
                      inlist=inlist, 
                      outlist=outlist) 
        cmds.append(['sudo', 'cp', dest, os.path.join(paths['etc'], os.path.basename(dest))])
        cmds.append(['rm', '-f', dest])

        cmds.append(['sudo', paths['a2ensite'], 'dashboard_wadqc'])

    if 'wad_api' in sitelist:
        # create proper paths in wsgi
        dest = os.path.join(installation_root, 'api_wadqc.wsgi')
        inlist  = ['__WADROOT__', '__XTRAPATHS__',  '__VENVBIN__', '\\']
        outlist = [installation_root, str(xtra_paths), venvbin,     '/']
        copy_replaces(src=os.path.join(paths['wsgi'], 'api_wadqc.wsgi'), 
                      dest=dest, 
                      inlist=inlist, 
                      outlist=outlist) 
        cmds.append(['sudo', 'cp', dest, os.path.join(paths['var'], os.path.basename(dest))])
        cmds.append(['rm', '-f', dest])

        # create proper paths in conf
        dest = os.path.join(installation_root, 'api_wadqc.conf')
        # the multi-listen bug pops up is a port is defined in ports.conf and in Listen
        port = int(portlist[pos['wad_api']])
        if port in nolisten:
            listen = "#Listen"
        else:
            listen = "Listen"

        inlist  = ['__LISTEN__',  '__USER__',   '__GROUP__', '__PORT__',  '\\']
        outlist = [listen,       user,          user,       str(port),  '/']
        copy_replaces(src=os.path.join(paths['conf'], 'api_wadqc.conf'), 
                      dest=dest, 
                      inlist=inlist, 
                      outlist=outlist) 
        cmds.append(['sudo', 'cp', dest, os.path.join(paths['etc'], os.path.basename(dest))])
        cmds.append(['rm', '-f', dest])
        
        cmds.append(['sudo', paths['a2ensite'], 'api_wadqc'])

    return cmds

def apache2_deploy_sites(sitelist, portlist, installation_root, **kwargs):
    #http://flask.pocoo.org/docs/0.12/deploying/mod_wsgi/
    logger.info('Deploying sites {}...'.format(', '.join(sitelist)))
    result,msg = ("OK","")

    paths = {
        'var': '/var/www/wadqc',
        'etc': '/etc/apache2/sites-available',
        'wsgi': os.path.join('scripts', 'templates'),
        'conf': os.path.join('scripts', 'templates'),
        'a2ensite': which('a2ensite')
    }

    # make sure var folder exists
    cmds = [['sudo', 'mkdir', '-p', paths['var']]]
    cmds.append(['sudo', 'a2dissite', '000-default']) # disable default
    
    # 3. get commands to deploy the sites
    cmds.extend(_deploy_sites(paths, sitelist, portlist, installation_root, **kwargs))

    # 4. restart apache
    cmds.append(['sudo', 'apachectl', 'restart']) # restart apache2 with updated site list

    for cmd in cmds:
        result, msg = external_call(cmd, returnoutput=True)
        mustquit = (not result == "OK")
        if mustquit:
            if 'Could not reliably determine the server' in msg:
                result = "OK"
                msg = ""
            else:
                errormsg = 'ERROR! Could not deploy_sites sites on apache2! '
                return result, errormsg+msg

    return result, msg

def httpd_deploy_sites(sitelist, portlist, installation_root, **kwargs):
    """
    source url:     # https://www.tecmint.com/apache-virtual-hosting-in-centos/
    Follow the Ubuntu approach to enable/disable virtual hosts
    """
    logger.info('Deploying sites {}...'.format(', '.join(sitelist)))
    result,msg = ("OK","")
    
    import getpass
    user = getpass.getuser() # gets the name of the user running this shell
    
    # 1. add a2ensite, a2dissite and a2query
    bindir = os.path.expanduser("~/.local/bin")
    cmds = [
        ['sudo', 'mkdir', '-p', bindir]
    ]

    for a2 in ['a2ensite', 'a2dissite', 'a2query']:
        dest = os.path.join(bindir, a2)
        cmds.extend([
            ['sudo', 'cp', os.path.join(os.getcwd(), 'scripts', 'templates', 'centos7', a2), dest],
            ['sudo', 'chmod', '+x', dest]
        ])

    # 2. create extra folders in etc/httpd and add to httpd conf
    etcpath = '/etc/httpd/sites-available'
    varpath = '/var/www/wadqc'
    cmds.extend([
        ['sudo', 'mkdir', '-p', varpath], # make sure var folder exists
        ['sudo', 'mkdir', '-p', etcpath],
        ['sudo', 'mkdir', '-p', '/etc/httpd/sites-enabled'],
        ['sudo', 'cp', '/etc/httpd/conf/httpd.conf', '/tmp/httpd.conf'], # we need to append something to this file
        ['sudo', 'chown', '{}:{}'.format(user,user), '/tmp/httpd.conf']
    ])
    
    # execute what we have now, because we need to change something
    for cmd in cmds:
        result, msg = external_call(cmd, returnoutput=True)
        mustquit = (not result == "OK")
        if mustquit:
            if 'Could not reliably determine the server' in msg:
                result = "OK"
                msg = ""
            else:
                errormsg = 'ERROR! Could not create files for httpd! '
                return result, errormsg+msg

    with open('/tmp/httpd.conf', 'a') as fio:
        fio.write("\nIncludeOptional sites-enabled/*.conf\n")

    cmds = [
        ['sudo', 'cp', '/tmp/httpd.conf', '/etc/httpd/conf/httpd.conf'], 
    ]    
    # 3. get commands to deploy the sites
    paths = {
        'var': '/var/www/wadqc',
        'etc': '/etc/httpd/sites-available',
        'wsgi': os.path.join('scripts', 'templates'),
        'conf': os.path.join('scripts', 'templates', 'centos7'),
        'a2ensite': os.path.join(bindir, 'a2ensite')
    }
    cmds.extend(_deploy_sites(paths, sitelist, portlist, installation_root, **kwargs))

    # 4. restart apache
    cmds.append(['sudo', 'systemctl', 'restart', 'httpd']) # restart httpd with updated site list

    for cmd in cmds:
        result, msg = external_call(cmd, returnoutput=True)
        mustquit = (not result == "OK")
        if mustquit:
            if 'Could not reliably determine the server' in msg:
                result = "OK"
                msg = ""
            else:
                errormsg = 'ERROR! Could not deploy_sites sites on httpd! '
                return result, errormsg+msg

    return result, msg

def firewall_add_port(portlist, **kwargs):
    """
    CentOS specific
    """
    logger.info('Setting up firewall rules...')

    # install firewalld
    result, msg = yum_install(['firewalld'])
    if result == "ERROR":
        return result, msg

    # enable firewall
    cmds = [
        ['sudo', 'systemctl', 'enable', 'firewalld'],
        ['sudo', 'systemctl', 'start', 'firewalld'],
    ]
    for cmd in cmds:
        result, msg = external_call(cmd, returnoutput=True, background=False)
        mustquit = (not result == "OK")
        if mustquit:
            if 'Created symlink' in msg:
                result = "OK"
                msg = ""
            else:
                errormsg = 'ERROR! Could not enable firewall!'
                return result, errormsg+msg
    
    cmds = []
    for port in portlist:
        cmds.append( ['sudo', 'firewall-cmd', '--permanent', '--add-port='+str(port)+'/tcp' ] )
    cmds.append( ['sudo', 'firewall-cmd', '--reload' ] )
    
    for cmd in cmds:
        #logger.info("{}".format(' '.join(cmd)))
        result, msg = external_call(cmd, returnoutput=True)
        mustquit = (not result == "OK")
        if mustquit:
            if 'ALREADY_ENABLED' in msg:
                result = "OK"
                msg = ""
            else:
                errormsg = 'ERROR! Could not open firewall port! {}'.format( errormsg = 'ERROR! Could not open firewall port! {}'.format( ' '.join(cmd)))
                return result, errormsg+msg

    return result, msg


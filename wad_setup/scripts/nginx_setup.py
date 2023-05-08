import os
import sys
import logging
from .helpers import external_call, apt_install, yum_install, pip_install
from .folders_settings import copy_replaces
from .which import which
from .systemd_setup import create_start_systemd
from .defaults import LOGGERNAME
logger = logging.getLogger(LOGGERNAME)

"""
Output files for running flask websites in nginx
Will need sudo.
"""

def enable_nginx(mode, **kwargs):
    """
    nginx is not enabled by default
    """
    logger.info('Enabling nginx...')
    result,msg = ("OK","")
    
    #1. install nginx and mods
    result,msg = apt_install(['nginx'])

    if result == "ERROR":
        return result, msg

    #2. install uwsgi 
    result, msg = pip_install(['uwsgi'], **kwargs)
    if result == 'ERROR':
        return result, msg

    # add wad user to the postgres group
    import getpass
    user = getpass.getuser() # gets the name of the user running this shell

    cmd = ['sudo', 'usermod', '-a', '-G', 'www-data', user] # add wad user to the webserver group
    result, msg = external_call(cmd)
    if result == "ERROR":
        return result, msg
    
    #2. enable dormant nginx
    if mode == 'systemd': # default for Ubuntu 16.04 and later
        cmds = [
            ['sudo', 'systemctl', 'enable', 'nginx'],
            ['sudo', 'systemctl', 'start', 'nginx'],
        ]
    else:
        result = "ERROR"
        msg = "Only systemd is implemented right now!"
        return result, msg

    for cmd in cmds:
        result, msg = external_call(cmd, returnoutput=True, background=False)
        mustquit = (not result == "OK")
        if mustquit:
            if "ynchronizing state of nginx.service" in msg:
                result = "OK"
            else:
                errormsg = 'ERROR! Could not enable nginx for {}! '.format(mode)
                return result, errormsg+msg
    
    return result, msg

def _deploy_sites(paths, sitelist, portlist, installation_root, **kwargs):
    """
    helper function generating the commands to copy the wsgi and conf scripts of sites
    http://flask.pocoo.org/docs/0.12/deploying/mod_wsgi/
    """
    multi_listen = kwargs.get("multi-listen", True)
    if multi_listen:
        listen = "Listen"
    else:
        listen = "#Listen"
        
    logger.info('...Deploying sites {}...Multi-listen: {}'.format(', '.join(sitelist), multi_listen))

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
        dest = os.path.join(installation_root, 'admin_wadqc.py')
        inlist  = ['__WADROOT__',   '__XTRAPATHS__', '__VENVBIN__', '\\']
        outlist = [installation_root, str(xtra_paths),    venvbin,       '/']
        copy_replaces(src=os.path.join(paths['wsgi'], 'admin_wadqc.wsgi'), 
                      dest=dest, 
                      inlist=inlist, 
                      outlist=outlist) 
        cmds.append(['sudo', 'cp', dest, os.path.join(paths['var'], os.path.basename(dest))])
        cmds.append(['rm', '-f', dest])

        # create proper paths in site
        dest = os.path.join(installation_root, 'admin_wadqc.site')
        # no __LISTEN__ param: always Listen
        inlist  = ['__SOCKETDIR__', '__PORT__',            '\\']
        outlist = [paths['sockdir'], str(portlist[pos['wad_admin']]),'/']
        copy_replaces(src=os.path.join(paths['conf'], 'admin_wadqc.site'), 
                      dest=dest, 
                      inlist=inlist, 
                      outlist=outlist)
        cmds.append(['sudo', 'cp', dest, os.path.join(paths['etc'], os.path.basename(dest))])
        cmds.append(['rm', '-f', dest])

        # create proper paths in uwsgi ini
        dest = os.path.join(installation_root, 'admin_wadqc.ini')
        inlist  = ['__SOCKETDIR__',                 '\\']
        outlist = [paths['sockdir'],'/']
        copy_replaces(src=os.path.join(paths['conf'], os.path.basename(dest)), 
                      dest=dest, 
                      inlist=inlist, 
                      outlist=outlist) 
        cmds.append(['sudo', 'cp', dest, os.path.join(paths['var'], os.path.basename(dest))])
        cmds.append(['rm', '-f', dest])

        cmds.append(['sudo', paths['nginx_ensite'], 'admin_wadqc'])
        
    if 'wad_dashboard' in sitelist:
        # create proper paths in wsgi
        dest = os.path.join(installation_root, 'dashboard_wadqc.py')
        inlist  = ['__WADROOT__',   '__VENVBIN__', '\\']
        outlist = [installation_root, venvbin,     '/']
        copy_replaces(src=os.path.join(paths['wsgi'], 'dashboard_wadqc.wsgi'), 
                      dest=dest, 
                      inlist=inlist, 
                      outlist=outlist) 
        cmds.append(['sudo', 'cp', dest, os.path.join(paths['var'], os.path.basename(dest))])
        cmds.append(['rm', '-f', dest])

        # create proper paths in site
        dest = os.path.join(installation_root, 'dashboard_wadqc.site')
        inlist  = ['__SOCKETDIR__', '__PORT__',                 '\\']
        outlist = [paths['sockdir'], str(portlist[pos['wad_dashboard']]),'/']
        copy_replaces(src=os.path.join(paths['conf'], 'dashboard_wadqc.site'), 
                      dest=dest, 
                      inlist=inlist, 
                      outlist=outlist) 
        cmds.append(['sudo', 'cp', dest, os.path.join(paths['etc'], os.path.basename(dest))])
        cmds.append(['rm', '-f', dest])

        # create proper paths in uwsgi ini
        dest = os.path.join(installation_root, 'dashboard_wadqc.ini')
        inlist  = ['__SOCKETDIR__',                 '\\']
        outlist = [paths['sockdir'],'/']
        copy_replaces(src=os.path.join(paths['conf'], os.path.basename(dest)), 
                      dest=dest, 
                      inlist=inlist, 
                      outlist=outlist) 
        cmds.append(['sudo', 'cp', dest, os.path.join(paths['var'], os.path.basename(dest))])
        cmds.append(['rm', '-f', dest])

        cmds.append(['sudo', paths['nginx_ensite'], 'dashboard_wadqc'])

    if 'wad_api' in sitelist:
        # create proper paths in wsgi
        dest = os.path.join(installation_root, 'api_wadqc.py')
        inlist  = ['__WADROOT__', '__XTRAPATHS__',  '__VENVBIN__', '\\']
        outlist = [installation_root, str(xtra_paths), venvbin,     '/']
        copy_replaces(src=os.path.join(paths['wsgi'], 'api_wadqc.wsgi'), 
                      dest=dest, 
                      inlist=inlist, 
                      outlist=outlist) 
        cmds.append(['sudo', 'cp', dest, os.path.join(paths['var'], os.path.basename(dest))])
        cmds.append(['rm', '-f', dest])

        # create proper paths in site
        dest = os.path.join(installation_root, 'api_wadqc.site')
        inlist  = ['__SOCKETDIR__', '__PORT__',                 '\\']
        outlist = [paths['sockdir'], str(portlist[pos['wad_api']]),'/']
        copy_replaces(src=os.path.join(paths['conf'], 'api_wadqc.site'), 
                      dest=dest, 
                      inlist=inlist, 
                      outlist=outlist) 
        cmds.append(['sudo', 'cp', dest, os.path.join(paths['etc'], os.path.basename(dest))])
        cmds.append(['rm', '-f', dest])
        
        # create proper paths in uwsgi ini
        dest = os.path.join(installation_root, 'api_wadqc.ini')
        inlist  = ['__SOCKETDIR__',                 '\\']
        outlist = [paths['sockdir'],'/']
        copy_replaces(src=os.path.join(paths['conf'], os.path.basename(dest)), 
                      dest=dest, 
                      inlist=inlist, 
                      outlist=outlist) 
        cmds.append(['sudo', 'cp', dest, os.path.join(paths['var'], os.path.basename(dest))])
        cmds.append(['rm', '-f', dest])

        cmds.append(['sudo', paths['nginx_ensite'], 'api_wadqc'])

    return cmds

def nginx_deploy_sites(sitelist, portlist, installation_root, **kwargs):
    #http://flask.pocoo.org/docs/0.12/deploying/mod_wsgi/
    logger.info('Deploying sites {}...'.format(', '.join(sitelist)))
    result,msg = ("OK","")

    import getpass
    user = getpass.getuser() # gets the name of the user running this shell

    # 1. add nginx_ensite, nginx_dissite and nginx_query
    bindir = os.path.expanduser("~/.local/bin")
    sockdir = os.path.expanduser(os.path.join(installation_root, 'sockets'))
    cmds = [
        ['mkdir', '-p', bindir],
        ['mkdir', '-p', sockdir],
        ['sudo', 'chown', '-R', '{}:www-data'.format(user), sockdir],
        ['sudo', 'chmod', '-R', 'g+rw', sockdir]
    ]

    for a2 in ['nginx_ensite', 'nginx_dissite', 'nginx_query']:
        dest = os.path.join(bindir, a2)
        cmds.extend([
            ['sudo', 'cp', os.path.join(os.getcwd(), 'scripts', 'templates', 'nginx', a2), dest],
            ['sudo', 'chmod', '+x', dest]
        ])


    paths = {
        'var': '/var/www/wadqc',
        'etc': '/etc/nginx/sites-available',
        'wsgi': os.path.join('scripts', 'templates'),
        'conf': os.path.join('scripts', 'templates', 'nginx'),
        'nginx_ensite': os.path.join(bindir, 'nginx_ensite'),
        'nginx_dissite': os.path.join(bindir, 'nginx_dissite'),
        'sockdir': sockdir 
    }

    # make sure var folder exists
    cmds.append(['sudo', 'mkdir', '-p', paths['var']])
    cmds.append(['sudo', paths['nginx_dissite'], 'default']) # disable default
    
    # 3. get commands to deploy the sites
    cmds.extend(_deploy_sites(paths, sitelist, portlist, installation_root, **kwargs))

    # 4. restart nginx
    cmds.append(['sudo', 'nginx', '-s', 'reload']) # restart nginx with updated site list

    for cmd in cmds:
        result, msg = external_call(cmd, returnoutput=True)
        mustquit = (not result == "OK")
        if mustquit:
            if 'Could not reliably determine the server' in msg:
                result = "OK"
                msg = ""
            else:
                errormsg = 'ERROR! Could not deploy_sites sites on nginx! '
                return result, errormsg+msg

    # 5. make systemd services
    for site in sitelist:
        result, msg = create_start_systemd(site, installation_root, **kwargs)
        mustquit = (not result == "OK")
        if mustquit:
            errormsg = 'ERROR! Could not create systemd for {} for nginx! '.format(site)
            return result, errormsg+msg

    return result, msg


import os.path
import logging
import getpass
from .distro import distro
from .which import which
from .helpers import external_call
from .defaults import LOGGERNAME
logger = logging.getLogger(LOGGERNAME)

"""
Output files for running processor and postgresql and orthanc by systemd
Will need sudo.

For Orthanc and wadprocessor in a virtualenv, create a wrapper script in <WADROOT>/WAD_QC
#!/bin/bash
source __VENVBIN__/activate
cd __WORKING_DIRECTORY__
exec __EXE__

"""

SERVICES = {
    'wadprocessor': {
        #[Unit]
        'Description': 'WAD-QC Processor',
        'After': 'syslog.target network.target wadpostgresql.service',
        'Requires': 'wadpostgresql.service',
        #[Service]
        'Type': 'simple',
        'User': 'wad',
        'Group': 'wad',
        'Restart': 'always',
        #'WorkingDirectory': '/home/wad/WADDEV/WAD_QC', # overwrite later
        'ExecStart': 'wadprocessor -i inifile --logfile_only', # overwrite later
        'ExecStop': 'wadcontrol quit', # overwrite later
        #[Install]
        'WantedBy': 'multi-user.target'
    },

    'wadpostgresql-permissions': {
        #[Unit]
        'Description': 'PostgreSQL for WAD-QC: arrange file permissions on /var/run/postgresql',
        'After': 'syslog.target network.target',
        'Before': 'wadpostgresql.service',
        #[Service]
        'Type': 'oneshot',
        'RemainAfterExit': 'yes', # service is valid even if exited
        'ExecStart': '/bin/chown -R user:user /var/run/postgresql /var/log/postgresql', # overwrite later
        'ExecStop': '/bin/chown -R postgres:postgres /var/run/postgresql', # change back to system default allows package upgrade
        #[Install]
        'WantedBy': 'multi-user.target'
    },

    'wadpostgresql': {
        #[Unit]
        'Description': 'PostgreSQL for WAD-QC',
        'After': 'syslog.target network.target',
        #[Service]
        'Type': 'forking',
        'User': 'wad',
        'Group': 'wad',
        'Restart': 'always',
        'PermissionsStartOnly': 'true', # run only the start command as user
        'ExecStartPre': [
            'mkdir -p /var/run/postgresql /var/log/postgresql', # make sure these folders exist
            '/bin/chown -R user:user /var/run/postgresql /var/log/postgresql', # overwrite later
            ],
        'ExecStart': 'pg_ctl -D PGDATA start', # overwrite later
        'ExecStop': 'pg_ctl -D PGDATA stop', # overwrite later
        'ExecStopPost': '/bin/chown -R postgres:postgres /var/run/postgresql', # change back to system default allows package upgrade
        #[Install]
        'WantedBy': 'multi-user.target'
    },
    'wadorthanc': {
        #[Unit]
        'Description': 'Orthanc for WAD-QC',
        'After': 'syslog.target network.target',
        #[Service]
        'Type': 'simple',
        'User': 'wad',
        'Group': 'wad',
        'Restart': 'always',
        'ExecStart': 'Orthanc orthanc.json', # overwrite later
        #[Install]
        'WantedBy': 'multi-user.target'
    },
    
    'wad_admin': { # uwsgi for nginx
        #[Unit]
        'Description': 'uWSGI instance to serve wadadmin of WAD-QC',
        'After': 'syslog.target network.target',
        #[Service]
        'Type': 'simple',
        'User': 'wad', # overwrite later
        'Group': 'www-data',
        'WorkingDirectory': '/var/www/wadqc',
        'Restart': 'always',
        'ExecStart': '/home/waduser/Envs/wad2env3/bin/uwsgi --ini admin_wadqc.ini', # overwrite later
        #[Install]
        'WantedBy': 'multi-user.target'
    },

    'wad_dashboard': { # uwsgi for nginx
        #[Unit]
        'Description': 'uWSGI instance to serve waddashboard of WAD-QC',
        'After': 'syslog.target network.target',
        #[Service]
        'Type': 'simple',
        'User': 'wad', # overwrite later
        'Group': 'www-data',
        'WorkingDirectory': '/var/www/wadqc',
        'Restart': 'always',
        'ExecStart': '/home/waduser/Envs/wad2env3/bin/uwsgi --ini dashboard_wadqc.ini', # overwrite later
        #[Install]
        'WantedBy': 'multi-user.target'
    },
    
    'wad_api': { # uwsgi for nginx
        #[Unit]
        'Description': 'uWSGI instance to serve wadapi of WAD-QC',
        'After': 'syslog.target network.target',
        #[Service]
        'Type': 'simple',
        'User': 'wad', # overwrite later
        'Group': 'www-data',
        'WorkingDirectory': '/var/www/wadqc',
        'Restart': 'always',
        'ExecStart': '/home/waduser/Envs/wad2env3/bin/uwsgi --ini api_wadqc.ini', # overwrite later
        #[Install]
        'WantedBy': 'multi-user.target'
    },
}

def create_wrapper(dest, venvbin, exe, cwd=None):
    import stat
    with open(dest, 'w') as fout:
        fout.write('#!/bin/bash\n')
        fout.write('source {}\n'.format(os.path.join(venvbin,'activate')))
        if not cwd is None:
            fout.write('cd {}\n'.format(cwd))
        fout.write('exec {}\n'.format(exe))

    try: # make executable
        os.chmod(dest, os.stat(dest).st_mode | stat.S_IEXEC)
    except Exception as e:
        logger.warning('cannot make {} executable'.format(os.path.basename(dest)))
    
def create_start_systemd(service, installation_root, **kwargs):
    """
    Create a systemd service configuration, enable it and start it now
    """
    logger.info("Creating systemd service for {}...".format(service))
    result, msg = ('OK', '')
    cmds = []
    user = getpass.getuser() # gets the name of the user running this shell

    wadroot = installation_root
    if wadroot is None:
        wadroot = os.environ.get('WADROOT', installation_root)
    if wadroot is None:
        result = "ERROR"
        msg = "Missing WADROOT definition. First run create_folders_settings!"
        return result, msg

    if service in SERVICES.keys():
        # create .service file
        serv = SERVICES[service]
        serv['User'] = user
        serv['Group'] = user
        if service == 'wadpostgresql':
            pgsdata = os.path.join(wadroot, 'pgsql', 'data')
            pg_ctl = 'pg_ctl'
            # find pg bindir; that is where pg_ctl is located.
            pgbindir = None
            cmd = ['pg_config', '--bindir']
            result2, pgbindir = external_call(cmd, returnoutput=True)
            if result2 == "OK":
                pg_ctl = os.path.join(pgbindir, pg_ctl)

            serv['ExecStartPre'] = [
                '-{} -p /var/run/postgresql /var/log/postgresql'.format(which('mkdir')),
                '-{} -R {}:{} /var/run/postgresql /var/log/postgresql'.format(which('chown'), user, user),
                ]
            serv['ExecStart'] = "{} -D {} start".format(pg_ctl, pgsdata)
            serv['ExecStop'] = "{} -D {} stop".format(pg_ctl, pgsdata)
            serv['ExecStopPost'] = "-{} -R postgres:postgres /var/run/postgresql".format(which('chown'))
            
            serv['OOMScoreAdjust'] = -900 # prevent OOM killer from choosing the postmaster
            
            # stop manually started postgres instance, so service can take over
            #cmd = [pg_ctl, '-D', pgsdata, 'stop']
            #result, msg = external_call(cmd, returnoutput=True, background=False)
            
        elif service == 'wadpostgresql-permissions':
            serv['ExecStart'] = '-{} -R {}:{} /var/run/postgresql /var/log/postgresql'.format(which('chown'), user, user)
            serv.pop('User', None) # need to run this with root permissions
            serv.pop('Group', None)
                        
        elif service == 'wadprocessor':
            if not "virtualenv" in kwargs.keys() or kwargs['virtualenv'].strip() == "": 
                exepath = '/home/{}/.local/bin'.format(user)
            else:
                exepath = os.path.abspath(os.path.expanduser(kwargs['virtualenv']))
                
            inifile = os.path.join(wadroot, 'WAD_QC', 'wadconfig.ini')
            serv['WorkingDirectory'] = "{}".format(os.path.join(wadroot, 'WAD_QC'))
            if not "virtualenv" in kwargs.keys() or kwargs['virtualenv'].strip() == "":
                serv['ExecStart'] = "{} -i {} --logfile_only".format(os.path.join(exepath, 'wadprocessor'), inifile)
                serv['ExecStop'] = "{} quit".format(os.path.join(exepath, 'wadcontrol'))
            else:
                # make a wrapper for wadprocessor and wadcontrol to start it from the given virtualenv
                dest_folder = os.path.join(wadroot, 'WAD_QC', 'systemd')
                if not os.path.exists(dest_folder):
                    os.makedirs(dest_folder)
                dest = os.path.join(dest_folder, 'wadprocessor_wrp')
                create_wrapper(dest, kwargs['virtualenv'], "{} -i {} --logfile_only".format(os.path.join(exepath, 'wadprocessor'), inifile))
                serv['ExecStart'] = dest
                dest = os.path.join(dest_folder, 'wadcontrol_wrp')
                create_wrapper(dest, kwargs['virtualenv'], "{} quit".format(os.path.join(exepath, 'wadcontrol')))
                serv['ExecStop'] = dest

        elif service == 'wadorthanc':
            orthanc = which('Orthanc')
            if orthanc is None:
                result = "ERROR"
                msg = "Cannot find Orthanc executable."
                return result, msg
            orthanc = os.path.abspath(orthanc)

            cfg = os.path.join(wadroot, 'orthanc', 'config', 'orthanc.json')
            logdir = os.path.join(wadroot, 'WAD_QC', 'Logs')

            if not "virtualenv" in kwargs.keys() or kwargs['virtualenv'].strip() == "":
                serv['ExecStart'] = "{} --logdir={} {}".format(orthanc, logdir, cfg)
            else:
                # make a wrapper for Orthanc to start it from the given virtualenv
                dest_folder = os.path.join(wadroot, 'WAD_QC', 'systemd')
                if not os.path.exists(dest_folder):
                    os.makedirs(dest_folder)
                dest = os.path.join(dest_folder, 'orthanc_wrp')
                create_wrapper(dest, kwargs['virtualenv'], "{} --logdir={} {}".format(orthanc, logdir, cfg))
                serv['ExecStart'] = dest
                
        #nginx
        elif service == 'wad_admin':
            if not "virtualenv" in kwargs.keys() or kwargs['virtualenv'].strip() == "": 
                exepath = '/home/{}/.local/bin'.format(user)
            else:
                exepath = os.path.abspath(os.path.expanduser(kwargs['virtualenv']))
                
            #serv['WorkingDirectory'] = "{}".format(os.path.join(wadroot, 'WAD_QC', 'sockets'))
            serv['Group'] = "www-data"
            serv['ExecStart'] = "{} --ini admin_wadqc.ini".format(os.path.join(exepath, 'uwsgi'))

        elif service == 'wad_dashboard':
            if not "virtualenv" in kwargs.keys() or kwargs['virtualenv'].strip() == "": 
                exepath = '/home/{}/.local/bin'.format(user)
            else:
                exepath = os.path.abspath(os.path.expanduser(kwargs['virtualenv']))
                
            #serv['WorkingDirectory'] = "{}".format(os.path.join(wadroot, 'WAD_QC', 'sockets'))
            serv['Group'] = "www-data"
            serv['ExecStart'] = "{} --ini dashboard_wadqc.ini".format(os.path.join(exepath, 'uwsgi'))

        elif service == 'wad_api':
            if not "virtualenv" in kwargs.keys() or kwargs['virtualenv'].strip() == "": 
                exepath = '/home/{}/.local/bin'.format(user)
            else:
                exepath = os.path.abspath(os.path.expanduser(kwargs['virtualenv']))
                
            #serv['WorkingDirectory'] = "{}".format(os.path.join(wadroot, 'WAD_QC', 'sockets'))
            serv['Group'] = "www-data"
            serv['ExecStart'] = "{} --ini api_wadqc.ini".format(os.path.join(exepath, 'uwsgi'))

        # continue
        dest = os.path.join(wadroot, "{}.service".format(service))
        
        with open(dest, "w") as fout:
            fout.write('[Unit]\n')
            for key in ['Description', 'After', 'Before', 'Requires']:
                if key in serv.keys(): fout.write('{}={}\n'.format(key, serv[key]))
            fout.write('\n[Service]\n')
            for key in ['Type', 'WorkingDirectory', 'User', 'Group',  'Restart', 'PermissionsStartOnly', 
                        'ExecStartPre', 'ExecStart', 'ExecStartPost', 'RemainAfterExit',
                        'ExecStop', 'ExecStopPost', 'OOMScoreAdjust']:
                if key in serv.keys(): 
                    if isinstance(serv[key], list):
                        for val in serv[key]:
                            fout.write('{}={}\n'.format(key, val))
                    else:
                        fout.write('{}={}\n'.format(key, serv[key]))
            fout.write('\n[Install]\n')
            for key in ['Alias', 'WantedBy']:
                if key in serv.keys(): fout.write('{}={}\n'.format(key, serv[key]))

        # set correct .service file location
        cmds.append(['sudo', 'mv', dest, os.path.join('/lib/systemd/system',os.path.basename(dest))])
        
        # always issue a sudo systemctl daemon-reload
        cmds.append(['sudo', 'systemctl', 'daemon-reload'])

        # start service at boot; not sure if this step must be skipped if service already enabled
        cmds.append(['sudo', 'systemctl', 'enable', service])

        # manually start service now; not sure if this step must be skipped if service already started
        cmds.append(['sudo', 'systemctl', 'start', service])
    else:
        result = 'ERROR'
        msg = 'Unknown Service {}'.format(service)
        
    for cmd in cmds:
        result, msg = external_call(cmd, returnoutput=True)
        mustquit = (not result == "OK")
        if mustquit:
            if 'Created symlink' in msg:
                result = "OK"
            else:
                errormsg = 'ERROR! Could not create and start systemd script for {}! '.format(service)
                return result, errormsg+msg

    return result, msg

def replace_systemd(**kwargs):
    """
    Use this only when running in docker, or in WSL under Windows 10. It replaces parts of systemd, so
    the command systemctl can be used when systemd is not fully supported. If systemd is full supported, 
    this will break your system!
    
    Replace /bin/systemctl with systemctl3.py
    Prevent overwriting of systemctl by preventing upgrades of systemd
    """
    dist = distro()

    result, msg = ('OK', '')

    logger = logging.getLogger(LOGGERNAME)
    logger.info("Replacing systemd command systemctl for {}...".format(dist['name']))

    logger.info("Preventing future updates to systemd...")
    if 'centos' in dist['distro'] or 'redhat' in dist['distro']:
        # append exclude=*systemd* to /etc/yum.conf
        srcfile = '/etc/yum.conf'
        tmpfile = '/tmp/cyum.conf'
        user = getpass.getuser() # gets the name of the user running this shell
        errormsg = 'ERROR! Could not prevent future updates to systemd! '
        
        cmds = [
            ['sudo', 'cp', srcfile, tmpfile], # we need to append something to this file
            ['sudo', 'chown', '{}:{}'.format(user,user), tmpfile]
        ]

        # execute what we have now, because we need to change something
        for cmd in cmds:
            result, msg = external_call(cmd, returnoutput=True)
            mustquit = (not result == "OK")
            if mustquit:
                return result, errormsg+msg

        # append line
        with open(tmpfile, 'a') as fio:
            fio.write("\nexclude=systemd\n")

        cmds = [
            ['sudo', 'cp', tmpfile, srcfile], 
        ]  
        for cmd in cmds:
            result, msg = external_call(cmd, returnoutput=True)
            mustquit = (not result == "OK")
            if mustquit:
                if 'Could not reliably determine the server' in msg:
                    result = "OK"
                    msg = ""
                else:
                    return result, errormsg+msg

        if result == "ERROR":
            return result, msg
        
    else: # debian or ubuntu
        # sudo apt-mark hold *systemd*
        errormsg = 'ERROR! Could not prevent future updates to systemd! '
        
        cmds = [
            ['sudo', 'apt-mark', 'hold', 'systemd'],
        ]

        # execute commands
        for cmd in cmds:
            result, msg = external_call(cmd, returnoutput=True)
            mustquit = (not result == "OK")
            if mustquit:
                return result, errormsg+msg
    

    # replace systemctl by python wrapper
    logger.info("Replacing systemctl...")
    srcfile  = os.path.join('scripts', 'files', 'systemd', 'systemctl3.py')
    destfile = "/usr/bin/systemctl"
    errormsg = 'ERROR! Could not replace systemctl! '

    cmds = [
        ['sudo', 'cp', srcfile, destfile],
        ['sudo', 'chmod', '+x', destfile]
    ]

    for cmd in cmds:
        result, msg = external_call(cmd, returnoutput=True)
        mustquit = (not result == "OK")
        if mustquit:
            return result, errormsg+msg

    return result, msg

def update_service(service, installation_root, tag, **kwargs):
    """
    Replace an exisiting wad service with an updated one. 
    Right now only wadpostgresql can be updated to include ExecStartPre to set ownership of some folders
    """
    if installation_root is None:
        return "ERROR", 'Cannot update services without supplying "WADROOT"'

    result, msg = ('OK', '')

    valid_services = ['wadpostgresql']
    if not service in valid_services:
        result = "ERROR"
        msg = "Cannot update service {}".format(service)
        return result, msg

    # make sure the backup folder exists
    backup_folder = os.path.join(installation_root, "WAD_QC", "upgraded")
    os.makedirs(backup_folder, exist_ok=True)

    if service == 'wadpostgresql':
        # move existing service to WADROOT/<service>.backup
        
        # make a backup of the original file
        src = os.path.join('/lib/systemd/system', "{}.service".format(service))
        dest = os.path.join(backup_folder, "{}.service.{}".format(service, tag))
        if os.path.exists(dest):
            msg = 'Refusing to upgrade "{}" because backup file "{}" already exists.'.format(service, dest)
            return "ERROR", msg
 
        import shutil
        try:
            shutil.copy(src, dest)
        except Exception as e:
            return "ERROR", str(e)

        # now just make a new systemd service, overwriting the existing one
        return create_start_systemd(service, installation_root, **kwargs)
        
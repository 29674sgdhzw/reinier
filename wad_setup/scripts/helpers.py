import os
import errno
import subprocess
import time
import logging
import sys
import platform
try:
    from .which import which # shutil.which only present for python3. for python2, use the one in wad_setup
except:
    from which import which

#----string/bytes conversion support for python2 and python3
import codecs
def string_as_bytes(x):
    return codecs.latin_1_encode(x)[0]
def bytes_as_string(x):
    return codecs.latin_1_decode(x)[0]

try:
    from scripts.defaults import LOGGERNAME
    from scripts.distro import distro
except:
    from .defaults import LOGGERNAME
    from .distro import distro

logger = logging.getLogger(LOGGERNAME)

def which2(command):
    """
    helper since this will not find ~/.local/bin if run by apache
    """
    cmd = which(command)
    if cmd is None:
        local_cmd = os.path.join(os.path.expanduser('~/.local/bin'), command)
        if os.path.exists(local_cmd):
            return local_cmd
        
    return cmd

def external_call(cmd, returnoutput=False, background=False, opt={}):
    """
    helper function to make system calls
    """
    result = 'OK'
    msg = ''
    try:
        if background:
            with open(os.devnull, "w") as f: # never pipe the output of a background process, as it will break eventually!
                proc = subprocess.Popen(cmd, stdout=f, stderr=f, close_fds=( not platform.system() == 'Windows' ), **opt)
                time.sleep(2)
                if proc.poll():
                    result = 'ERROR'
        else:
            # Now we can wait for the child to complete
            if opt.get('shell', False):
                cmd = ' '.join(cmd)
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **opt)
            (output, error) = proc.communicate()
            if returnoutput:
                if error: # this is true if any output to stderr is produced, e.g. by a numpy warning. 
                          #  to trigger only on real errors do if proc.returncode and returnoutput
                    msg = bytes_as_string(error.strip())
                    if 'Extracting templates from packages' in msg: # message from dpkg-preconfigure which is not an error
                        logger.warn('Ignoring message "{}"'.format(msg))
                        msg = bytes_as_string(output.strip())
                        result = 'OK'
                    elif 'RLIMIT_CORE' in msg: # error message when using sudo in containers
                        result = 'OK'
                        msg = ''
                    else:
                        result = 'ERROR'
                else:
                    msg = bytes_as_string(output.strip())
                    result = 'OK'
            else:
                result ='OK' if proc.returncode==0 else 'ERROR'

    except OSError as e:
        if e.errno != errno.ENOENT:
            msg = str(e)
            result = 'ERROR'
        else:
            msg = str(e)
            result = 'ERROR'

    except subprocess.CalledProcessError as e:
        msg = str(e)
        result = 'ERROR'

    return result, msg

def apt_update(**kwargs):
    """
    Apt update
    """
    msg = 'Updating the system-wide packages list needs root permission. If root permissions are needed, you will be prompted for your password.'
    logger.info(msg)
    cmd = ['sudo', 'apt-get', 'update']

    result, msg = external_call(cmd, returnoutput=True)

    # make sure apt is not locked by another process
    lockmsg = "ould not get lock"
    if lockmsg in msg:
        logger.info("Another apt/dpkg process is running. Waiting for that process to finish...")
        while lockmsg in msg:
            time.sleep(5) # not really useful to check more often, as most auto-update process are rather lengthy
            result, msg = external_call(cmd, returnoutput=True)
            
    # deal with time-out
    lockmsg = "emporary failure resolving"
    if lockmsg in msg:
        nret = 5
        logger.info("Time out resolving Ubuntu repository. Retrying {} more times in 5 seconds...".format(nret))
        while nret>0 and lockmsg in msg:
            logger.info("Time out resolving Ubuntu repository. Retrying in 5 seconds...")
            time.sleep(5) # not really useful to check more often, as most auto-update process are rather lengthy
            result, msg = external_call(cmd, returnoutput=True)
            nret -= 1
        
    return result, msg

def apt_install(pkgs, **kwargs):
    """
    Apt install pkgs
    kwargs must contain a list 'pkgs'
    """
    logger.info("Installing system packages: {}...".format(', '.join(pkgs)))
    # make sure apt list is updated; prevents errors like packeges not found
    # actually this is only needed the very first time apt_install is requested.
    result, msg = apt_update(**kwargs) 
    if result == "ERROR":
        if not "usual lecture" in msg:
            return result, msg
        else:
            logger.warn('Ignoring message "{}"'.format(msg))
        
    msg = 'Installing system-wide packages needs root permission. If root permissions are needed, you will be prompted for your password.'
    logger.info(msg)
    cmd = ['sudo', 'apt-get', 'install', '--no-install-recommends', '-y']
    cmd.extend(pkgs)

    result, msg = external_call(cmd, returnoutput=True)

    # make sure apt is not locked by another process
    lockmsg = "ould not get lock"
    if lockmsg in msg:
        logger.info("Another apt/dpkg process is running. Waiting for that process to finish...")
        while lockmsg in msg:
            time.sleep(5) # not really useful to check more often, as most auto-update process are rather lengthy
            result, msg = external_call(cmd, returnoutput=True)

    return result, msg

def yum_update(**kwargs):
    """
    Yum update
    """
    msg = 'Updating the system-wide packages list needs root permission. If root permissions are needed, you will be prompted for your password.'
    logger.info(msg)
    cmd = ['sudo', 'yum', 'update', '-y']

    result, msg = external_call(cmd, returnoutput=True)

    # make sure apt is not locked by another process
    lockmsg = "xisting lock"
    if lockmsg in msg:
        logger.info("Another yum process is running. Waiting for that process to finish...")
        while lockmsg in msg:
            time.sleep(5) # not really useful to check more often, as most auto-update process are rather lengthy
            result, msg = external_call(cmd, returnoutput=True)
    
    if "Trying other mirror" in msg and not "No more mirrors to try" in msg:
        result = "OK"

    return result, msg

def yum_install(pkgs, **kwargs):
    """
    Yum install pkgs
    kwargs must contain a list 'pkgs'
    """
    logger.info("Installing system packages: {}...".format(', '.join(pkgs)))

    # make sure yum list is updated; prevents errors like packeges not found
    # actually this is only needed the very first time yum_install is requested.
    result, msg = yum_update(**kwargs) 
    if result == "ERROR":
        if not "usual lecture" in msg:
            return result, msg
        else:
            logger.warn('Ignoring message "{}"'.format(msg))

    msg = 'Installing system-wide packages needs root permission. If root permissions are needed, you will be prompted for your password.'
    logger.info(msg)
    cmd = ['sudo', 'yum', 'install', '-y']
    cmd.extend(pkgs)

    return external_call(cmd, returnoutput=True)

def pip_upgrade_pip():
    # check if pip needs to upgrade itself
    # pip is installed as global package and needs root permission to upgrade itself
    pip = 'pip'
    if sys.version_info >= (3, 0): # python3
        pip = 'pip3'

    # dummy pip upgrade command to see if it can be upgraded
    cmd = ['sudo', pip, 'install', '--user', 'pip']
    result, msg = external_call(cmd, returnoutput=True, background=False, opt={})
    if result == 'ERROR':
        if 'install --upgrade pip' in msg:
            # pip can upgrade itself, try it
            msg = 'Trying to upgrade pip...'
            logger.info(msg)
            cmd = ['sudo', pip, 'install', '--upgrade', 'pip']
            result, msg = external_call(cmd, returnoutput=True, background=False, opt={})
            if result == 'ERROR':
                if 'entry deserialization failed' in msg:
                    # ignore caching problems, just means that it will be redownloaded
                    logger.warn('Ignoring message "{}"'.format(msg))
                    result = "OK"
                elif 'ython 3.5 reached the end of its life':
                    # ignore python 3.5 end-of-life
                    logger.warn('Ignoring message "{}"'.format(msg))
                    result = "OK"

    return result, msg

def get_latest_pkg(pkg):
    # helper to find the name of the latest version of the given package in a local folder
    import fnmatch, re

    folder = os.path.dirname(pkg)
    pattern = os.path.basename(pkg).replace('latest','*')
    matches = fnmatch.filter(os.listdir(folder), pattern)
    
    # sort by version number, instead of string sorting
    regexp_pattern = os.path.basename(pkg).replace('latest','(.*)')
    matches.sort(key=lambda s: list(map(int, re.search(regexp_pattern, s).group(1).split('.'))))
    
    return os.path.join(folder, matches[-1])
    
def pip_install(pkglist, **kwargs):
    #pip install --upgrade ~/wadinstall/dist/wad_qc-0.1.0-py2.py3-none-any.whl
    if isinstance(pkglist, str):
        pkglist = [pkglist]

    pip = 'pip'
    if sys.version_info >= (3, 0): # python3
        pip = 'pip3'

    result, msg = ("OK", "")
    for pkg in pkglist:
        if 'latest' in pkg:
            pkg = get_latest_pkg(pkg)

        if os.path.basename(pkg).startswith('wad_qc-'):
            result, msg = upgrade_wadqc(os.path.basename(pkg), **kwargs)
            if not result == "OK":
                return result, msg

        cmd = [pip, 'install', '--default-timeout=100']
        # check if we need to install in user's home
        if not "virtualenv" in kwargs.keys() or kwargs['virtualenv'].strip() == "": 
            if not 'VIRTUAL_ENV' in os.environ:
                cmd.append('--user') 
                if not '.local/bin' in os.environ['PATH']:
                    from scripts.addtoenv import addtoenv
                    addtoenv({'PATH': os.path.expanduser('~/.local/bin')})

        cmd.extend( ['--upgrade', pkg] )
        result, msg = external_call(cmd, returnoutput=True, background=False, opt={})
        if result == 'ERROR':
            # check if error was due to pip "You should consider upgrading" message
            if 'install --upgrade pip' in msg:
                # display the info but do not consider it error
                logger.info("{}: {}".format('NOTICE', msg))
                result = "OK"
                
                # platform dependent behaviour
                dist = distro()
                if 'centos' in dist['distro'] or 'redhat' in dist['distro']:
                    # CentOS7
                    logger.info("Installing EPEL repository: package epel-release:...")
                    # pip was installed globally, need to upgrade it globally
                    logger.info("{}".format("Upgrading pip ..."))
                    result_pup, msg_pup = pip_upgrade_pip()
                    if result_pup == 'ERROR':
                        logger.error("{}: {}".format(result_pup, msg_pup))
                        logger.info("{}".format("Upgrade pip failed, but will continue with wad_setup"))
                else:
                    # Ubuntu / other: upgrade pip like other packages
                    # allow recursive call to pip_install only once to prevent endless recursive call in case of error
                    if not 'pip' in pkglist:
                        pip_install(['pip'], **kwargs)
                        # don't check errors...
                    
            elif 'entry deserialization failed' in msg:
                # ignore caching problems, just means that it will be redownloaded
                logger.warn('Ignoring message "{}"'.format(msg))
                result = "OK"

            elif 'ailed to establish a new connection' in msg:
                # try again; probably already installed correctly, just a dangling warning.
                logger.warn('Received time-out trying to establish connection for pip install. Will try again.'.format(msg))
                result, msg = external_call(cmd, returnoutput=True, background=False, opt={})

            elif 'ython 3.5 reached the end of its life':
                # ignore python 3.5 end-of-life
                logger.warn('Ignoring message "{}"'.format(msg))
                result = "OK"
                
    return result, msg

def pip_install_requirements(**kwargs):
    """
    pip install -r requirements.txt
    This will create a replicated, tested base environment

    """
    logger.info("Installing python required modules...")
    pip = 'pip'
    requirements = 'requirements2.txt'
    
    if sys.version_info >= (3, 0): # python3
        pip = 'pip3'
        requirements = 'requirements3.txt'
    if sys.version_info < (3, 6): # python3.5
        requirements = 'requirements35.txt'
    result, msg = ("OK", "")

    requirements = os.path.join(kwargs['__setup_folder'], requirements)

    cmd = [pip, 'install', '-r', requirements]

    # check if we need to install in user's home
    if not "virtualenv" in kwargs.keys() or kwargs['virtualenv'].strip() == "": 
        if not 'VIRTUAL_ENV' in os.environ:
            cmd.append('--user') 
            if not '.local/bin' in os.environ['PATH']:
                from scripts.addtoenv import addtoenv
                addtoenv({'PATH': os.path.expanduser('~/.local/bin')})

    result, msg = external_call(cmd, returnoutput=True, background=False, opt={})
    if result == 'ERROR':
        if 'pip install --upgrade pip' in msg:
            pip_install(['pip'], **kwargs)
            result = "OK"
        elif 'ython 3.5 reached the end of its life':
            # ignore python 3.5 end-of-life
            logger.warn('Ignoring message "{}"'.format(msg))
            result = "OK"
        else:
            return result, msg

    return result, msg

def unpack_from_url(pkgurl, dstfolder, remove_old=False):
    """
    Download a file from the given url, and unpack in given destination folder, optionally remove the old contents.
    """
    import requests
    import tarfile #zipfile zipfile does not preserve permissions
    import shutil
    from io import BytesIO

    result, msg = ('OK', '')

    try:
        # get stream handle
        pkg = requests.get(pkgurl, stream=True)
        total_length = pkg.headers.get('content-length')

        if remove_old:
            # remove old installation
            if os.path.exists(dstfolder):
                shutil.rmtree(p, ignore_errors=True)

        with BytesIO() as f:
            if total_length is None: # no content length header
                f.write(pkg.content)
            else:
                dl = 0
                total_length = int(total_length)
                for data in pkg.iter_content(chunk_size=4096):
                    dl += len(data)
                    f.write(data)
                    logger.info("downloading... %.2f" % (100*dl/total_length))

            f.seek(0)
            zfile = tarfile.open(fileobj=f, mode='r:gz')
            logger.info('extracting package...')
            zfile.extractall(path=os.path.expanduser(dstfolder))

    except Exception as e:
        result = 'ERROR'
        msg = str(e)
        return result, msg

    return result, msg

def port_available(port):
    """
    Check if tcp port is in use
    """
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        s.bind(('localhost', port))
    except socket.error:
        return False

    s.close()

    return True

def clean_permissions_wadroot(wadroot_folders, using_nginx):
    """
    remove group permissions and other permissions from WADROOT
    """
    result,msg = "OK",""
    import stat

    nomode = stat.S_IRWXG | stat.S_IRWXO
    for wadroot in wadroot_folders:
        logger.info("Removing group and other permissions from {}...".format(wadroot))
        count_d = 0
        count_f = 0
        for root, dirs, files in os.walk(wadroot):
            for d in dirs:
                da = os.path.join(root, d)
                if not os.path.islink(da):
                    if using_nginx and os.path.join(wadroot, 'sockets') == da:
                        pass
                    else:
                        try:
                            current = stat.S_IMODE(os.stat(da).st_mode)
                            if not (current & ~nomode) == current:
                                os.chmod(da, current & ~nomode)
                                count_d += 1
                        except Exception as e:
                            msg += "{}; ".format(str(e))
            if using_nginx and os.path.join(wadroot, 'sockets') == root:
                continue

            for f in files:
                fa = os.path.join(root, f)
                if not os.path.islink(fa):
                    try:
                        current = stat.S_IMODE(os.stat(fa).st_mode)
                        if not (current & ~nomode) == current:
                            os.chmod(fa, current & ~nomode)
                            count_f += 1
                    except Exception as e:
                        msg += "{}; ".format(str(e))

        logger.info("...Corrected permissions of {} folders and {} files in {}.".format(count_d, count_f, wadroot))

    return result,msg

def platform_fixes(fixes, **kwargs):
    """
    apply indicated platform specific fixes. See the Troubleshooting_for_installation section
    on the wiki.
    """
    import getpass
    user = getpass.getuser() # gets the name of the user running this shell

    result,msg = "OK",""
    
    if "removeipc" in fixes:
        # fix posgresql exiting after logout of waduser
        # in /etv/systemd/logind.conf add RemoveIPC=no
        # this needs a reboot of the system to take effect
        logger.info("Fixing RemoveIPC...")
        srcfile = '/etc/systemd/logind.conf'
        tmpfile = '/tmp/logind.conf'
        cmds = [
            ['sudo', 'cp', srcfile, tmpfile], # we need to append something to this file
            ['sudo', 'chown', '{}:{}'.format(user,user), tmpfile]
        ]

        # execute what we have now, because we need to change something
        for cmd in cmds:
            result, msg = external_call(cmd, returnoutput=True)
            mustquit = (not result == "OK")
            if mustquit:
                errormsg = 'ERROR! Could fix RemoveIPC! '
                return result, errormsg+msg

        # make sure "RemoveIPC" is set to "no"
        with open(tmpfile, 'r') as fio:
            lines = fio.readlines()
        with open(tmpfile, "w") as fio:
            has_login = False
            for line in lines:
                if line.strip().startswith("[Login]"):
                    has_login = True
                if line.strip().startswith('RemoveIPC'): # if this line is commented out, it is ignored
                    fio.write('# '+ line)
                else:
                    fio.write(line)

            if not has_login:
                fio.write("[Login]\n")
            fio.write("RemoveIPC=no\n")

        cmds = [
            ['sudo', 'cp', tmpfile, srcfile], 
            ['sudo', 'systemctl', 'daemon-reload'],
            # ['sudo', 'systemctl', 'restart', 'systemd-logind'], # this may result in corrupted display, loosing display etc 
        ]    
        for cmd in cmds:
            result, msg = external_call(cmd, returnoutput=True)
            mustquit = (not result == "OK")
            if mustquit:
                errormsg = 'ERROR! Could fix RemoveIPC! '
                return result, errormsg+msg

        if result == "ERROR":
            return result, msg
    
    if "enable-linger" in fixes:
        # prevent killing of background processes if waduser logs out
        # loginctl enable-linger waduser
        logger.info("Fixing enable-linger...")

        cmd = ['sudo', 'loginctl', 'enable-linger', user]
        result, msg = external_call(cmd, returnoutput=True)
        if "No such file" in msg:
            result = "OK"
        if result == "ERROR":
            return result, msg

    if "nginxtimeout" in fixes:
        return "OK", "nginx timeout already fixed per site"

    if "apache2timeout" or "httpdtimeout" in fixes:
        # for time consuming jobs, an apache time-out can occur (def = 5min)
        # according to several sources, apache2.4.6 which is used in CentOS7 has a
        # bug that hardcodes 30s as timeout, without looking at the Timeout param.
        if "apache2timeout" in fixes:
            apache_name = "apache2"
            srcfile = '/etc/apache2/apache2.conf'
            tmpfile = '/tmp/apache2.conf'
            restartcmd = ['sudo', 'apachectl', 'restart'] 
        else:
            apache_name = "httpd"
            srcfile = '/etc/httpd/conf/httpd.conf'
            tmpfile = '/tmp/chttpd.conf'
            restartcmd = ['sudo', 'systemctl', 'restart', 'httpd']
            
        logger.info("Fixing {} time-out...".format(apache_name))
        cmds = [
            ['sudo', 'cp', srcfile, tmpfile], # we need to append something to this file
            ['sudo', 'chown', '{}:{}'.format(user,user), tmpfile]
        ]

        # execute what we have now, because we need to change something
        for cmd in cmds:
            result, msg = external_call(cmd, returnoutput=True)
            mustquit = (not result == "OK")
            if mustquit:
                errormsg = 'ERROR! Could not fix {} time-out! '.format(apache_name)
                return result, errormsg+msg

        # make sure "Timeout" is set to 50 minutes "3000"
        with open(tmpfile, 'r') as fio:
            lines = fio.readlines()
        with open(tmpfile, "w") as fio:
            found = False
            for line in lines:
                if line.strip().startswith('Timeout'): # if this line is commented out, it is ignored
                    fio.write('# '+ line)
                    fio.write("Timeout 3000\n")
                    found = True
                else:
                    fio.write(line)

            if not found:
                fio.write("Timeout 3000\n")

        cmds = [
            ['sudo', 'cp', tmpfile, srcfile], 
            restartcmd 
        ]  
        for cmd in cmds:
            result, msg = external_call(cmd, returnoutput=True)
            mustquit = (not result == "OK")
            if mustquit:
                if 'Could not reliably determine the server' in msg:
                    logger.warn('Ignoring message "{}"'.format(msg))

                    result = "OK"
                    msg = ""
                else:
                    errormsg = 'ERROR! Could not fix {} time-out! '.format(apache_name)
                    return result, errormsg+msg

        if result == "ERROR":
            return result, msg
    
        
    return result,msg

def restrict_privileges(**kwargs):
    """
    The waduser only needs full priviliges for installation. After installation, it is sufficient to
    have priviliges only for enabling/disabling apache/nginx sites and for systemctl to start/stop
    postgresql, orthanc and apache/nginx.
    """
    import getpass
    user = getpass.getuser() # gets the name of the user running this shell

    result,msg = "OK",""
    
    # make sure we are not root!
    if os.name == 'nt':
        pass
    elif os.geteuid() == 0:
        msg = "Refusing to restrict the priviliges of user '{}' because '{}' = 'root'.".format(user, user)
        return "ERROR", msg

    cmds = []

    #check if user is part of sudo/wheel group; if so, we remove that membership at the end of the script.
    sudo_grp = []
    import grp
    group_names = set(
        g.gr_name for g in grp.getgrall() if user in g.gr_mem
    )

    dist = distro()
    if 'centos' in dist['distro'] or 'redhat' in dist['distro']:
        # CentOS7
        if "wheel" in group_names:
            sudo_grp.append("wheel")
    else:
        # Ubuntu
        if "sudo" in group_names:
            sudo_grp.append("sudo")
        
    if len(sudo_grp) == 0:
        msg = "User '{}' is not a member of a common sudo group. Cannot restrict priviliges for this user.".format(user)
        return "ERROR",msg

    """
    ceate file  /etc/sudoers.d/waduser
    set mode to 0440
    contents:
      waduser ALL = (root) /usr/bin/systemctl, /usr/sbin/a2ensite, /usr/sbin/a2dissite
    """
    # build list of wanted access files
    acc_list = []
    for c in ['systemctl', 'a2ensite', 'a2dissite', 'nginx_ensite', 'nginx_dissite']:
        c2 = which2(c)
        if not c2 is None:
            acc_list.append(c2)

    tmpfile = '/tmp/wad.privs'
    dstfile = '/etc/sudoers.d/waduser'
    with open(tmpfile, 'w') as fio:
        fio.write("{} ALL = (root) {}\n".format(
        user, ", ".join(acc_list)))
    cmds = [
        ['sudo', 'cp', tmpfile, dstfile], # we need to append something to this file
        ['sudo', 'chmod', '0440', dstfile],
        ['sudo', 'rm', '-f', tmpfile]
    ]

    for grp in sudo_grp:
        cmd = ["sudo", "gpasswd", "-d", user, grp]
        cmds.append(cmd)

    for cmd in cmds:
        result, msg = external_call(cmd, returnoutput=True)
        mustquit = (not result == "OK")
        if mustquit:
            errormsg = 'Could not fully restrict priviliges for {}! '.format(user)
            return result, errormsg+msg
        
    if len(sudo_grp)>0:
        logger.warning("Sudo priviliges of '{}' have been revoked. Please logout and login again for these changes to take effect.".format(user))
        
    return result,msg

def upgrade_wadqc(newpkg, **kwargs):
    """
    define some extra actions to be performed when upgrading wad_qc
    """

    import pkg_resources
    try:
        current_whl = pkg_resources.get_distribution("wad_qc").version
    except pkg_resources.DistributionNotFound:
        return "OK", ""

    installation_root = kwargs.get('installation_root', None)
    if installation_root is None:
        installation_root = os.environ.get('WADROOT', None)

    #wad_qc-0.1.0-py2.py3-none-any.whl
    new_whl = newpkg.split('-')[1]
    
    if pkg_resources.parse_version(new_whl) <= pkg_resources.parse_version(current_whl):
        msg = 'No additional steps needed upgrading wad_qc from "{}" to "{}"'.format(current_whl, new_whl)
        logger.info(msg)
        return "OK", msg
    
    if ( pkg_resources.parse_version(new_whl) >= pkg_resources.parse_version('2.0.12') and 
         pkg_resources.parse_version(current_whl)< pkg_resources.parse_version('2.0.12') ):
        """
        2.0.12: systemd_setup.update_service('wadpostgresql')
        """
        service = 'wadpostgresql'
        src = os.path.join('/lib/systemd/system', "{}.service".format(service))
        if os.path.exists(src):
            # typically systemd services for WAD-QC do not exist on a DEV system
            from . import systemd_setup as act
            result, msg = act.update_service(service, installation_root, 'pre_{}'.format(new_whl), **kwargs)
            if not result == "OK":
                return result, msg

            msg = 'Upgraded systemd service "{}"'.format(service)
            logger.info(msg)
            return "OK", msg

    msg = 'No additional steps needed upgrading wad_qc from "{}" to "{}"'.format(current_whl, new_whl)
    logger.info(msg)
    return "OK", msg
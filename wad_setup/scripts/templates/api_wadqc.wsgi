#!/usr/bin/env python
import sys
from os import environ, path, makedirs

# Activate virtual env located in user's home
venvbin = __VENVBIN__
if not venvbin is None:
    activate_env = path.expanduser(path.join(venvbin,'activate_this.py')) #~/Envs/wad2env3/bin/activate_this.py
    if sys.version_info < (3,):
        execfile(activate_env, dict(__file__=activate_env))
    else:
        with open(activate_env) as file_:
            exec(file_.read(), dict(__file__=activate_env))

# application will find inifile from environment
environ['WADROOT'] = '__WADROOT__'
from wad_api.run import _setup_logging
from wad_api.app import flask_app as application
_setup_logging(application, path.join('__WADROOT__', 'WAD_QC'), levelname='INFO')
from __future__ import print_function
import platform
import os
import shutil
import logging

try:
   from .defaults import LOGGERNAME
except:
   from defaults import LOGGERNAME
   
logger = logging.getLogger(LOGGERNAME)

STARTWAD = '\n# -- WADQC -- BEGIN\n'
ENDWAD = '# --  WADQC -- END\n'
def copy_wadqc_from_bash(dest, wadenv):
   """
   Extract the STARTWAD ENDWAD part
   """
   if platform.system() == 'Darwin':
      src = os.path.expanduser('~/.bash_profile')
   else:
      src = os.path.expanduser('~/.bashrc')

   with open(src, 'r') as f:
      contents = f.read()

   if not STARTWAD in contents:
      pre_stuff = contents
      in_stuff = ''
      post_stuff = ''
   else:
      pre_stuff = contents.split(STARTWAD)[0]
      in_stuff = contents.split(STARTWAD)[1].split(ENDWAD)[0]
      post_stuff = contents.split(ENDWAD)[-1]
   
   with open(dest, 'w') as f:
      f.write('{}{}{}'.format(STARTWAD, in_stuff, ENDWAD)) #post_stuff
      #f.write('{}{}\n{}'.format(ENDWAD, line, post_stuff))
      if not wadenv is None:
         f.write('export WAD2ENV3="{}"\n'.format(wadenv))

def get_and_backup_bash():
   if platform.system() == 'Darwin':
      src = os.path.expanduser('~/.bash_profile')
   else:
      src = os.path.expanduser('~/.bashrc')
   num = 0
   dst = '{}-wad.{}.bak'.format(src, num)
   if os.path.exists(dst): # always keep original before any wadqc modding
      num = 1 # this will be the previous wadqc modded version
      dst = '{}-wad.{}.bak'.format(src, num)
      
   # make a copy of the original
   shutil.copy(src, dst)
   return src

def removefrombash(line):
   result, msg = ("OK", "")

   if platform.system() == 'Linux' or platform.system() == 'Darwin':
      src = get_and_backup_bash()
  
      with open(src, 'r') as f:
         contents = f.read()
      
      # if line not in bashrc, return
      if not line.strip() in contents:
         return result, msg

      contents = contents.replace(line, '')

      with open(src, 'w') as f:
         f.write('{}'.format(contents))

def addtobash(line):
   result, msg = ("OK", "")

   if platform.system() == 'Linux' or platform.system() == 'Darwin':
      src = get_and_backup_bash()
  
      with open(src, 'r') as f:
         contents = f.read()
      
      # if line already in bashrc, return
      if line.strip() in contents:
         return result, msg

      if not STARTWAD in contents:
         pre_stuff = contents
         in_stuff = ''
         post_stuff = ''
      else:
         pre_stuff = contents.split(STARTWAD)[0]
         in_stuff = contents.split(STARTWAD)[1].split(ENDWAD)[0]
         post_stuff = contents.split(ENDWAD)[-1]
      
      with open(src, 'w') as f:
         f.write('{}{}{}'.format(pre_stuff, STARTWAD, in_stuff))
         f.write('{}{}\n{}'.format(ENDWAD, line, post_stuff))
   
def addtoenv(kv_dict):
    # add to path; holds only for current process, but prevents new shell and restart installer
   result, msg = ("OK", "")

   if platform.system() == 'Linux' or platform.system() == 'Darwin':
      src = get_and_backup_bash()
  
      with open(src, 'r') as f:
         contents = f.read()
      if not STARTWAD in contents:
         pre_stuff = contents
         in_stuff = ''
         post_stuff = ''
      else:
         pre_stuff = contents.split(STARTWAD)[0]
         in_stuff = contents.split(STARTWAD)[1].split(ENDWAD)[0]
         post_stuff = contents.split(ENDWAD)[-1]
      
      with open(src, 'w') as f:
         # build a list of already defined WAD-QC export variables
         in_dict = {}
         in_stuff_left = ''
         for line in in_stuff.split('\n'):
            if line.strip().startswith('export '): # export a = "b"
               lin = line.split('export ')[1] # a = "b"
               key = lin.split('=')[0].strip() # a
               if key == 'PATH': # leave path settings alone
                  in_stuff_left += '{}\n'.format(line)
               else:
                  val = '='.join(lin.split('=')[1:]).strip()
                  in_dict[key] = val
               
         f.write('{}{}{}'.format(pre_stuff, STARTWAD, in_stuff_left))
         for key, value in kv_dict.items():
            if key == 'PATH':
               if not value in os.environ['PATH']:
                  f.write('export PATH={}:$PATH\n'.format(value))
                  # also add to current environment
                  os.environ['PATH'] = value+os.pathsep+os.environ['PATH']

            else: # add to output
               in_dict[key] = value # overwrite old setting
               # also add to current environment
               os.environ[key] = value
            
         for key, value in in_dict.items():
            if value.startswith('"') or value.startswith("'"):
               f.write('export %s=%s\n'%(key,value))
            else:
               f.write('export %s="%s"\n'%(key,value))

         f.write('{}{}'.format(ENDWAD,post_stuff))

   elif platform.system() == 'Windows':
      try:
         import _winreg
      except ImportError:
         import winreg as _winreg
     
      for key, value in kv_dict.items():
         """
         Add Python to the search path on Windows
         
         This is based on win_add2path.py of the miniconda3 installation.
         
         win_add2path.py has the following copyright notice:
         Copyright (c) 2008 by Christian Heimes <christian@cheimes.de>
         Licensed to PSF under a Contributor Agreement.
         """
         if key == "PATH":
            HKCU = _winreg.HKEY_CURRENT_USER
            ENV = "Environment"
            PATH = "PATH"
            DEFAULT = u"%PATH%"
         
            with _winreg.CreateKey(HKCU, ENV) as key:
               try:
                  envpath = _winreg.QueryValueEx(key, PATH)[0]
               except WindowsError:
                  envpath = DEFAULT
         
               paths = [envpath]
               if value and value not in envpath and os.path.isdir(value):
                  paths.append(value)
         
               envpath = os.pathsep.join(paths)
               _winreg.SetValueEx(key, PATH, 0, _winreg.REG_EXPAND_SZ, envpath)
         else:
            HKCU = _winreg.HKEY_CURRENT_USER
            ENV = "Environment"
            PATH = key
            
            with _winreg.CreateKey(HKCU, ENV) as key:
               _winreg.SetValueEx(key, PATH, 0, _winreg.REG_EXPAND_SZ, value)
            
   else:
      result = "ERROR"
      msg = 'Unknown platform {}'.format(platform.system())
      logger.error(msg)
      
   return result, msg
        


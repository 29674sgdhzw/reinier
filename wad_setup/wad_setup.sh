#!/usr/bin/env bash
# prefer python as this will resolve to the correct python binary in a virtualenv
for shell in python python3 python2; do
    if command -v "${shell}" &>/dev/null; then
        /usr/bin/env "${shell}" "scripts/wad_setup.py" "$@";
        ans=$?
        if [[ ans -eq 210 ]]; then 
            # only created venv, restart script in wad2env3
            echo "[=====] Automatically restarting wad_setup in newly created virtualenv."
            source .venvsetup
            source "$WORKON_HOME/$WAD2ENV3/bin/activate"
            /usr/bin/env "${shell}" "scripts/wad_setup.py" "$@";
            ans=$?
        fi
        if [[ ans -eq 230 ]]; then 
            # requested to restart wadservices
            echo "[=====] Automatically restarting wadservices in virtualenv."
            source .venvsetup
            source "$WORKON_HOME/$WAD2ENV3/bin/activate"
            export PATH=$HOME/bin:$HOME/.local/bin:$PATH
            wadservices -c restart;
            echo "[=====] If you just installed WAD-QC for the first time, logout and login again for the changes to user '$USER' to take effect."
        fi
        if [[ ans -eq 240 ]]; then 
            # requested to upgrade dbwadqc and restart wadservices
            echo "[=====] Automatically upgrading dbwadqc "
            source .venvsetup
            source "$WORKON_HOME/$WAD2ENV3/bin/activate"
            export PATH=$HOME/bin:$HOME/.local/bin:$PATH
            waddoctor --dbupgrade dbwadqc;
            echo "[=====] Automatically restarting wadservices in virtualenv."
            wadservices -c restart;
        fi
        exit $ans; 
    fi
done
# We didn't find any of them.
echo "ERROR! Need to have python, python3, or python2 installed and in your path!"
exit 1

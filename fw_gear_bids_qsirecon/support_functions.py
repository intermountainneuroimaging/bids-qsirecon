import logging
import os
import subprocess as sp
import re
import shutil
import tempfile
from typing import List


log = logging.getLogger(__name__)

# -----------------------------------------------
# Support functions
# -----------------------------------------------

def generate_command(
        gear_options: dict,
        app_options: dict,
) -> List[str]:
    """Build the main command line command to run.

    This method should be the same for FW and XNAT instances. It is also BIDS-App
    generic.

    Args:
        gear_options (dict): options for the gear, from config.json
        app_options (dict): options for the app, from config.json
    Returns:
        cmd (list of str): command to execute
    """

    cmd = []
    cmd.append(gear_options["feat"]["common_command"])
    cmd.append(app_options["design_file"])

    return cmd


def execute_shell(cmd, dryrun=False, cwd=os.getcwd()):
    log.info("\n %s", cmd)
    if not dryrun:
        terminal = sp.Popen(
            cmd,
            shell=True,
            stdout=sp.PIPE,
            stderr=sp.PIPE,
            universal_newlines=True,
            cwd=cwd
        )
        stdout, stderr = terminal.communicate()
        returnCode = terminal.poll()
        log.debug("\n %s", stdout)
        log.debug("\n %s", stderr)

        if stderr:
            log.warning("Error. \n%s\n%s", stdout, stderr)
            returnCode = 1
        return returnCode


def searchfiles(path, dryrun=False, exit_on_errors=True) -> list[str]:
    cmd = "ls -d " + path

    log.debug("\n %s", cmd)

    if not dryrun:
        terminal = sp.Popen(
            cmd, shell=True, stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True
        )
        stdout, stderr = terminal.communicate()
        returnCode = terminal.poll()
        log.debug("\n %s", stdout)
        log.debug("\n %s", stderr)

        files = stdout.strip("\n").split("\n")

        if returnCode > 0 and exit_on_errors:
            log.error("Error. \n%s\n%s", stdout, stderr)

        if returnCode > 0 and not exit_on_errors:
            log.warning("Warning. \n%s\n%s", stdout, stderr)

        return files


def sed_inplace(filename, pattern, repl):
    """
    Perform the pure-Python equivalent of in-place `sed` substitution: e.g.,
    `sed -i -e 's/'${pattern}'/'${repl}' "${filename}"`.
    """
    # For efficiency, precompile the passed regular expression.
    pattern_compiled = re.compile(pattern)

    # For portability, NamedTemporaryFile() defaults to mode "w+b" (i.e., binary
    # writing with updating). This is usually a good thing. In this case,
    # however, binary writing imposes non-trivial encoding constraints trivially
    # resolved by switching to text writing. Let's do that.
    with tempfile.NamedTemporaryFile(dir=os.getcwd(), mode='w', delete=False) as tmp_file:
        with open(filename) as src_file:
            for line in src_file:
                tmp_file.write(pattern_compiled.sub(repl, line))

    # Overwrite the original file with the munged temporary file in a
    # manner preserving file attributes (e.g., permissions).
    shutil.copystat(filename, tmp_file.name)
    shutil.move(tmp_file.name, filename)


def locate_by_pattern(filename, pattern):
    """
    Locates all instances that meet pattern and returns value from file.
    Args:
        filename: text file
        pattern: regex

    Returns:

    """
    # For efficiency, precompile the passed regular expression.
    pattern_compiled = re.compile(pattern)
    arr = []
    with open(filename) as src_file:
        for line in src_file:
            num = re.findall(pattern_compiled, line)
            if num:
                arr.append(num[0])

    return arr


def replace_line(filename, pattern, repl):
    """
        Perform the pure-Python equivalent of in-place `sed` substitution: e.g.,
        `sed -i -e 's/'${pattern}'/'${repl}' "${filename}"`.
        """
    # For efficiency, precompile the passed regular expression.
    pattern_compiled = re.compile(pattern)

    # For portability, NamedTemporaryFile() defaults to mode "w+b" (i.e., binary
    # writing with updating). This is usually a good thing. In this case,
    # however, binary writing imposes non-trivial encoding constraints trivially
    # resolved by switching to text writing. Let's do that.
    with tempfile.NamedTemporaryFile(dir=os.getcwd(), mode='w', delete=False) as tmp_file:
        with open(filename) as src_file:
            for line in src_file:
                if re.findall(pattern_compiled, line):
                    tmp_file.write(repl)
                else:
                    tmp_file.write(line)

    # Overwrite the original file with the munged temporary file in a
    # manner preserving file attributes (e.g., permissions).
    shutil.copystat(filename, tmp_file.name)
    shutil.move(tmp_file.name, filename)

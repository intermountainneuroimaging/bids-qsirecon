"""Parser module to parse gear config.json."""
from typing import Tuple

from flywheel_gear_toolkit import GearToolkitContext

from utils.fly.set_performance_config import set_mem_gb, set_n_cpus
import tempfile
import subprocess as sp
from flywheel_gear_toolkit import GearToolkitContext
import os
import logging
from pathlib import Path

log = logging.getLogger(__name__)

def parse_config(
    gear_context: GearToolkitContext,
) -> Tuple[dict, dict]:
    """Parse the config and other options from the context, both gear and app options.

    Returns:
        gear_options: options for the gear
        app_options: options to pass to the app
    """
    # ##   Gear config   ## #

    gear_options = {
        "bids-app-binary": gear_context.manifest.get("custom").get("bids-app-binary"),
        # These are the BIDS modalities that will be downloaded from the instance
        "bids-app-modalities": gear_context.manifest.get("custom").get(
            "bids-app-modalities"
        ),
        "analysis-level": gear_context.manifest.get("custom").get("analysis-level"),
        "save-intermediate-output": gear_context.config.get(
            "gear-save-intermediate-output"
        ),
        "intermediate-files": gear_context.config.get("gear-intermediate-files"),
        "intermediate-folders": gear_context.config.get("gear-intermediate-folders"),
        "keep-output": gear_context.config.get("gear-keep-output"),
        "dry-run": gear_context.config.get("gear-dry-run"),
        "output-dir": gear_context.output_dir,
        "destination-id": gear_context.destination["id"],
        "work-dir": gear_context.work_dir,
        "client": gear_context.client,
    }

    # set the output dir name for the BIDS app:
    gear_options["output_analysis_id_dir"] = (
        gear_options["output-dir"] / gear_options["destination-id"] / Path("bids")
    )

    # ##   App options:   ## #

    # pylint: disable=pointless-string-statement
    """ Notes on inputs:  Generic pipeline inputs may be passed using 'bids_app_args'. Specific named inputs also incldued below.

    * Positional arguments are covered by the template
    * participant-label: SKIPPED extracted from parent container
    * session-id: SKIPPED extracted from parent container
    * datasets: EXCLUDED inferred from clean workdir 
    * bids-filter-file: SKIPPED for now (TODO)
    * bids-database-dir: SKIPPED for now (TODO)
    * ncpus: SKIPPED for now
    * output-resolution: ADDED
    * input-type: ADDED choose from options (qsiprep|ukb|hcpya)
    * work-dir: ADDED (cause error in html generation if excluded)
    * atlases: ADDED Selection of atlases to apply to the data. Built-in atlases include: AAL116, AICHA384Ext, Brainnetome246Ext, Gordon333Ext, and the 4S atlases.
    All other options from the "Options" section are left out, as these can be
    passed into the "bids_app_args" section
    """
    # pylint: enable=pointless-string-statement

    app_options_keys = [
        "bids_app_args",
        "output-resolution",
        "recon-spec",
        "input-type",
        "atlases",
        "n_cpus",
        "mem_mb",
        "verbose"
    ]
    app_options = {key: gear_context.config.get(key) for key in app_options_keys}

    app_options["n_cpus"] = set_n_cpus(app_options["n_cpus"] or 0)
    # qsiprep only takes integers:
    app_options["mem_mb"] = int(1024 * set_mem_gb((app_options["mem_mb"] or 0) / 1024))

    rs_path = gear_context.get_input_path("recon-spec")
    if rs_path:
        app_options["recon-spec"] = rs_path

    preproc_path = gear_context.get_input("preprocessing-pipeline-zip")
    if preproc_path:
        analysis = gear_context.client.get_container(preproc_path["hierarchy"]["id"])
        file = gear_context.client.get_file(preproc_path["object"]["file_id"])
        download_and_unzip_inputs(analysis, file, gear_options["work-dir"])

    work_dir = gear_options["work-dir"]
    if work_dir:
        app_options["work-dir"] = work_dir

    # get input directory for gear
    gear_options["input-dir"] = os.path.join(gear_options["work-dir"], "".join([x for x in next(os.walk(gear_options["work-dir"]))[1] if x in ["qsiprep","ukb","hcpya"]]))

    #always add resource monitor
    app_options["resource-monitor"] = True

    # pull original file structure
    orig = []
    for path, subdirs, files in os.walk(gear_options["work-dir"]):
        for name in files:
            orig.append(os.path.join(path, name))

    gear_options["unzipped-files"] = orig

    return gear_options, app_options


# SUPPORT FUNCTIONS !!
def download_and_unzip_inputs(parent_obj, file_obj, path):
    """
    unzip_inputs unzips the contents of zipped gear output into the working
    directory.
    Args:
        zip_filename (string): The file to be unzipped
    """
    rc = 0
    outpath = []

    os.makedirs(path, exist_ok=True)

    # start by checking if zipped file
    if ".zip" not in file_obj.name:
        return

    # next check if the zip file is organized with analysis id as top dir
    zip_info = parent_obj.get_file_zip_info(file_obj.name)
    zip_top_dir = Path(zip_info.members[0].path).parts[0]
    if len(zip_top_dir) == 24:
        # this is an archive zip and needs to be handled special
        with tempfile.TemporaryDirectory(dir=path) as tempdir:
            zipfile = os.path.join(tempdir, file_obj.name)

            # download zip
            file_obj.download(zipfile)

            # use linux "unzip" methods in shell in case symbolic links exist
            log.info("Unzipping file, %s", os.path.basename(zipfile))
            cmd = ["unzip", "-qq", "-o", zipfile, "-d", tempdir]
            result = sp.run(cmd, check=True, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
            log.info("Done unzipping.")

            try:
                # use subprocess shell command here since there is a wildcard
                cmd = "mv " + os.path.join(tempdir, zip_top_dir, "*") + " " + str(path)
                result = sp.run(cmd, shell=True, check=True, stdout=sp.PIPE, stderr=sp.PIPE)
            except sp.CalledProcessError as e:
                cmd = "cp -R " + os.path.join(tempdir, zip_top_dir, "*") + " " + str(path)
                result = sp.run(cmd, shell=True, check=True, stdout=sp.PIPE, stderr=sp.PIPE)
            finally:
                cmd = ['rm', '-Rf', os.path.join(tempdir, zip_top_dir)]
                run_command_with_retry(cmd, delay=5)
    else:
        path = os.path.join(path, "files")
        os.makedirs(path, exist_ok=True)
        zipfile = os.path.join(path, file_obj.name)
        # download zip
        file_obj.download(zipfile)
        # use linux "unzip" methods in shell in case symbolic links exist
        log.info("Unzipping file, %s", os.path.basename(zipfile))
        cmd = ["unzip", "-qq", "-o", zipfile, "-d", path]
        result = sp.run(cmd, check=True, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
        log.info("Done unzipping.")
        os.remove(zipfile)

    return str(path)


def run_command_with_retry(cmd, retries=3, delay=1, cwd=os.getcwd()):
    """Runs a command with retries and delay on failure."""

    for attempt in range(retries):
        try:
            result = sp.run(cmd, check=True, stdout=sp.PIPE, stderr=sp.PIPE, text=True, cwd=cwd)
            return result
        except sp.CalledProcessError as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                raise  # Re-raise the exception if all retries fail
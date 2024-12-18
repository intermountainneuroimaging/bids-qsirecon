#!/usr/bin/env python
"""The run script."""
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import List, Tuple, Union
import glob
from utils.flywheel_bids.results.zip_intermediate import (
    zip_all_intermediate_output,
    zip_intermediate_selected,
)
from utils.flywheel_bids.utils.download_run_level import download_bids_for_runlevel
from utils.flywheel_bids.utils.run_level import get_analysis_run_level_and_hierarchy
from flywheel_gear_toolkit import GearToolkitContext
from flywheel_gear_toolkit.licenses.freesurfer import install_freesurfer_license
from flywheel_gear_toolkit.utils.file import sanitize_filename
from flywheel_gear_toolkit.utils.metadata import Metadata
from flywheel_gear_toolkit.utils.zip_tools import zip_output

# This design with the main interfaces separated from a gear module (with main and
# parser) allows the gear module to be publishable, so it can then be imported in
# another project, which enables chaining multiple gears together.
from fw_gear_bids_qsirecon.main import prepare, run
from fw_gear_bids_qsirecon.parser import parse_config
from utils.dry_run import pretend_it_ran
from utils.zip_htmls import zip_htmls

from utils.singularity import run_in_tmp_dir

# The gear is split up into 2 main components. The run.py file which is executed
# when the container runs. The run.py file then imports the rest of the gear as a
# module.

log = logging.getLogger(__name__)

# Default/fall-back folder for the FS license (in case ${FREESURFER_HOME} is not defined
# in the environment:
FREESURFER_HOME = "/opt/freesurfer"
# FREESURFER_HOME = "./freesurfer"

os.chdir("/flywheel/v0")


# pylint: disable=too-many-arguments
def post_run(
    gear_name: str,
    gear_options: dict,
    analysis_output_dir: Union[str, Path],
    run_label: str,
    errors: List[str],
    warnings: List[str],
) -> None:
    """Move all the results to the final destination, clean-up.

    Args:
        gear_name (str): gear name, used in the output file names
        gear_options (dict): gear options
        analysis_output_dir (str or Path): name of the output dir
        run_label (str): run label (project|subject|session label)
        errors (list[str]): list of errors found
        warnings (list[str]): list of warnings found
    """
    # zip entire output/<analysis_id> folder into
    #  <gear_name>_<project|subject|session label>_<analysis.id>.zip
    zip_file_name = f"{gear_name}_{run_label}_{gear_options['destination-id']}.zip"

    exclude_files = [i.replace(str(gear_options["work-dir"]) + os.sep, '') for i in set(gear_options["unzipped-files"])]

    zip_output(
        str(gear_options["output-dir"]),
        gear_options["destination-id"],
        zip_file_name,
        dry_run=gear_options["dry-run"],
        exclude_files=exclude_files,
    )

    # zip any .html files in output/<analysis_id>/
    for html_dir in glob.glob(str(Path(analysis_output_dir) / "derivatives" / "qsirecon*")):
        zip_htmls(str(gear_options["output-dir"]), gear_options["destination-id"], html_dir)

    # possibly save ALL intermediate output
    if gear_options["save-intermediate-output"]:
        zip_all_intermediate_output(
            gear_options["destination-id"],
            gear_name,
            gear_options["output-dir"],
            gear_options["work-dir"],
            run_label,
        )

    # possibly save intermediate files and folders
    zip_intermediate_selected(
        gear_options["intermediate-files"],
        gear_options["intermediate-folders"],
        gear_options["destination-id"],
        gear_name,
        gear_options["output-dir"],
        gear_options["work-dir"],
        run_label,
    )

    # clean up: remove output that was zipped
    if Path(analysis_output_dir).exists():
        if not gear_options["keep-output"]:

            log.debug('removing output directory "%s"', str(analysis_output_dir))
            shutil.rmtree(analysis_output_dir)

        else:
            log.info('NOT removing output directory "%s"', str(analysis_output_dir))

    else:
        log.info("Output directory does not exist so it cannot be removed")

    # Report errors and warnings at the end of the log, so they can be easily seen.
    if len(warnings) > 0:
        msg = "Previous warnings:\n"
        for warn in warnings:
            msg += "  Warning: " + str(warn) + "\n"
        log.info(msg)

    if len(errors) > 0:
        msg = "Previous errors:\n"
        for err in errors:
            if str(type(err)).split("'")[1] == "str":
                # show string
                msg += "  Error msg: " + str(err) + "\n"
            else:  # show type (of error) and error message
                err_type = str(type(err)).split("'")[1]
                msg += f"  {err_type}: {str(err)}\n"
        log.info(msg)


# pylint: enable=too-many-arguments


# pylint: disable=too-many-locals,too-many-statements
def main(context: GearToolkitContext):
    FWV0 = Path.cwd()
    log.info("Running gear in %s", FWV0)
    output_dir = context.output_dir
    log.info("output_dir is %s", output_dir)
    work_dir = context.work_dir
    log.info("work_dir is %s", work_dir)


    #initiat return_code
    return_code = 0

    """Parses config and runs."""
    # For now, don't allow runs at the project level:
    destination = context.client.get(context.destination["id"])
    if destination.parent.type == "project":
        log.exception(
            "This version of the gear does not run at the project level. "
            "Try running it for each individual subject."
        )
        # sys.exit(1)
        return_code = 1


    # Errors and warnings will always be logged when they are detected.
    # Keep a list of errors and warning to print all in one place at end of log
    # Any errors will prevent the BIDS App from running.
    errors = []
    warnings = []

    # Call the fw_gear_bids_qsiprep.parser.parse_config function
    # to extract the args, kwargs from the context (e.g. config.json).
    gear_options, app_options = parse_config(context)

    # #adding the usual environment call
    # environ = get_and_log_environment()


    # TO-DO: install_freesurfer_license from the gear_toolkit takes the gear context as
    #    an argument, so it is only valid for FW instances. However, the functionality
    #    of taking a FreeSurfer license (either string or file) and copying it to
    #    wherever your app expects it should be the same whether you run it on FW, or
    #    XNAT or HPC or locally.
    #    In the future, it would be great to have a "instance-independent"
    #    install_freesurfer_license and have a "instance-dependent" function to extract
    #    the license from the context. At that point, we could extract the license e.g.
    #    in the parser, and this function can be moved to fw_gear_bids_qsiprep.main
    # Constants that do not need to be changed
    FREESURFER_LICENSE = "./freesurfer/license.txt"
    # MAKE SURE FREESURFER LICENSE IS FOUND
    os.environ["FS_LICENSE"] = str(FWV0 / "freesurfer/license.txt")

    #Now install the license
    install_freesurfer_license(
        context,
        FREESURFER_LICENSE,
    )

    # TemplateFlow seems to be baked in to the container since 2021-10-07 16:25:12 so this is not needed...actually, it is for now...
    templateflow_dir = FWV0 / "templateflow"
    templateflow_dir.mkdir(parents=True, exist_ok=True)
    os.environ["SINGULARITYENV_TEMPLATEFLOW_HOME"] = str(templateflow_dir)
    os.environ["TEMPLATEFLOW_HOME"] = str(templateflow_dir)
    orig = Path("/home/qsiprep/.cache/templateflow/")
    # Fill writable templateflow directory with existing templates so they don't have to be downloaded
    templates = list(orig.glob("*"))
    for tt in templates:
        # (templateflow_dir / tt.name).symlink_to(tt)
        shutil.copytree(tt, templateflow_dir / tt.name, dirs_exist_ok = True)

    prepare_errors, prepare_warnings = prepare(
        gear_options=gear_options,
        app_options=app_options,
    )
    errors += prepare_errors
    warnings += prepare_warnings

    if len(errors) == 0:
        destination = gear_context.client.get(gear_context.destination["id"])
        subject = gear_context.client.get(destination.parents.subject)
        session = gear_context.client.get(destination.parents.session)
        subject_label = subject.label
        session_label = session.label

        # For BIDS-Apps that run at the participant level, set the
        # "participant_label" from the container from which it was launched.
        if gear_options["analysis-level"] == "participant" and not app_options.get(
            "participant_label", ""
        ):
            app_options["participant_label"] = subject_label

        # In general, BIDS-Apps take only the (subject) label, without the "sub-" part:
        if app_options["participant_label"].startswith("sub-"):
            # Write this in two instructions because if you write it in one, Black will
            # format it horribly:
            new_participant_label = app_options["participant_label"][len("sub-") :]
            app_options["participant_label"] = new_participant_label

    if len(errors) > 0:
        e_code = 1
        log.info("Command was NOT run because of previous errors.")

    elif gear_options["dry-run"]:
        e_code = 0
        pretend_it_ran(gear_options, app_options)
        e = "gear-dry-run is set: Command was NOT run."
        log.warning(e)
        warnings.append(e)

    else:
        try:
            # Pass the args, kwargs to fw_gear_qsiprep.main.run function to execute
            # the main functionality of the gear.
            e_code = run(gear_options, app_options)

        except RuntimeError as exc:
            e_code = 1
            errors.append(str(exc))
            log.critical(exc)
            log.exception("Unable to execute command.")

    # Cleanup, move all results to the output directory.
    # post_run should be run regardless of dry-run or exit code.
    # It will be run even in the event of an error, so that the partial results are
    # available for debugging.
    post_run(
        gear_name=context.manifest["name"],
        gear_options=gear_options,
        analysis_output_dir=str(gear_options["output_analysis_id_dir"]),
        run_label=subject_label,
        errors=errors,
        warnings=warnings,
    )

    gear_builder = context.manifest.get("custom").get("gear-builder")
    # gear_builder.get("image") should be something like:
    # flywheel/bids-qsiprep:0.0.1_0.15.1
    container = gear_builder.get("image").split(":")[0]
    log.info("%s Gear is done.  Returning %s", container, e_code)

    # Exit the python script (and thus the container) with the exit
    # code returned by fw_gear_bids_qsiprep.main.run function.
    # sys.exit(e_code)
    return_code = e_code
    return return_code


# pylint: enable=too-many-locals,too-many-statements


# Only execute if file is run as main, not when imported by another module
if __name__ == "__main__":  # pragma: no cover
    # Get access to gear config, inputs, and sdk client if enabled.
    with GearToolkitContext() as gear_context:

        # # Initialize logging, set logging level based on `debug` configuration
        # # key in gear config.
        gear_context.init_logging()
        log.parent.handlers[0].setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))

        if gear_context.config["gear-log-level"] == "DEBUG":
            log.setLevel(logging.DEBUG)

        if gear_context.config["gear-log-level"] == "INFO":
            log.setLevel(logging.INFO)

        if gear_context.config["gear-log-level"] == "WARNING":
            log.setLevel(logging.WARNING)

        if gear_context.config["gear-log-level"] == "ERROR":
            log.setLevel(logging.ERROR)

        scratch_dir = run_in_tmp_dir(gear_context.config["gear-writable-dir"])
    # Has to be instantiated twice here, since parent directories might have
    # changed
    with GearToolkitContext() as gear_context:

        # Pass the gear context into main function defined above.
        return_code = main(gear_context)
    # clean up (might be necessary when running in a shared computing environment)
    if scratch_dir:
        log.debug("Removing scratch directory")
        for thing in scratch_dir.glob("*"):
            if thing.is_symlink():
                thing.unlink()  # don't remove anything links point to
                log.debug("unlinked %s", thing.name)
        shutil.rmtree(scratch_dir)
        log.debug("Removed %s", scratch_dir)

    sys.exit(return_code)

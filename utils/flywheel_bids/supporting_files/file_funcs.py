import logging
import os.path as op
import typing
from pathlib import Path

import flywheel
from flywheel_gear_toolkit import GearToolkitContext
from flywheel_gear_toolkit.utils.curator import HierarchyCurator
from flywheel_gear_toolkit.utils.walker import Walker

log = logging.getLogger(__name__)


def is_file_match(
    filename: flywheel.FileEntry,
    intent: str = None,
    features: list = None,
    measurement: str = None,
):
    """
    Check if the scan is an MR image. Optionally, narrow down the
    results to only the measurement of interest (i.e., T1)
    """
    # Get rid of localizers
    if not filename.get("classification"):
        return False

    arg_dict = {"Intent": [intent], "Measurement": [measurement], "Features": features}
    check_passes = []
    for k, v in arg_dict.items():
        if filename.get("classification", {}).get(k) and v:
            if isinstance(filename.get("classification", {}).get(k), list):
                param_set = set(filename.get("classification", {}).get(k))
            elif isinstance(filename.get("classification", {}).get(k), str):
                param_set = set([filename.get("classification", {}).get(k)])
            if set(v).isdisjoint(param_set):
                return False

    return True


class FileFinder(HierarchyCurator):
    """A curator to find files on the session containers"""

    def __init__(
        self,
        *args,
        intent: str = None,
        features: list = None,
        measurement: str = None,
        gear_context: GearToolkitContext = None,
        **kwargs,
    ):
        super(FileFinder, self).__init__(*args, **kwargs)
        self.intent = intent
        self.measurement = measurement
        self.features = features
        self.files = []
        self.acquisitions = []
        self.gear_context = gear_context

    def curate_acquisition(self, acquisition: flywheel.Acquisition):
        """Override the empty method in curator.py"""
        for f in acquisition.files:
            if is_file_match(
                filename=f,
                intent=self.intent,
                features=self.features,
                measurement=self.measurement,
            ):
                self.files.append(f)

    def curate_session(self, session: flywheel.Session):
        """Override the empty method in curator.py"""
        # reset the file collection
        self.files = []
        for acq in session.acquisitions.iter_find():
            self.curate_acquisition(acq)


def copy_matching_sbrefs(gear_context: GearToolkitContext):
    """
    Find all the functional and SBRef scans. If there are the same number of
    scans, then nothing will be modified. If there are fewer SBRefs than fMRIs,
    then this method will attempt to copy the SBRef to match each fMRI.
    """
    # Get the root_dir for the sessions, acquisitions, etc.
    destination_parent = gear_context.get_destination_parent()

    funcs = list_func_scans(destination_parent)
    sbrefs = list_sbref_scans(destination_parent)

    # One only needs to copy sbrefs, if there is a numerical mismatch
    if len(funcs) != len(sbrefs):
        list_funcs = [f.name for f in funcs]
        list_sbrefs = [f.name for f in sbrefs]
        # Remove the "_sbref" entity so that potential functional matches can be found.
        list_sbrefs = clean_sbrefs(list_sbrefs)

        # Figure out which functionals need a copy of sbrefs
        diff = list(set(list_funcs) - set(list_sbrefs))
        if len(sbrefs) == 1:
            for func_scan in diff:
                new_sb_name = create_sbref_name(sbrefs[0], func_scan)
                # Create the name where the sbref can live for a quick second
                tmp_sb_filename = op.join(gear_context.work_dir, new_sb_name)
                copy_single_sbref(sbrefs[0], tmp_sb_filename, func_scan)
        else:
            log.error(
                "SBRefs need to be manually sorted to match the\n"
                "intended target acquisitions."
            )


def clean_sbrefs(sbrefs: list):
    """In order for the functional scan names to be compared,
    the '_sbref' portion of the filename needs to be removed."""
    clean_list = []
    for sbref in sbrefs:
        ext = "".join(Path(sbref).suffixes)
        sbref = sbref.replace(ext, "")
        if sbref.endswith("_sbref"):
            clean_list.append(sbref.replace("_sbref", "") + ext)
        else:
            clean_list.append(sbref + ext)
    return clean_list


def copy_single_sbref(
    sbref: flywheel.FileEntry,
    tmp_sb_filename: typing.Union[str, Path],
    matching_func_scan: flywheel.FileEntry,
):
    """Pull the original sbref down to the working directory, locate the matching acquisition info, and upload
    the sbref to that acquisition."""
    sbref.download(tmp_sb_filename)
    acq_container = matching_func_scan.parent
    acq_container.upload_file(tmp_sb_filename)


def create_sbref_name(
    sbref_name: typing.Union[str, Path], func_name: typing.Union[str, Path]
):
    """Use the functional scan name as the stem for the sbref, so that BIDS apps can find the corresponding sbref
    automatically."""
    new_sb_base = op.splitext(func_name)[0]
    if "." in new_sb_base:
        new_sb_base = op.splitext(new_sb_base)[0]
    orig_sb_ext = ".".join(op.basename(sbref_name).split(".")[1:])
    new_sb_name = new_sb_base + "_sbref." + orig_sb_ext
    return new_sb_name


def get_matching_files(
    root, intent=None, measurement=None, features=None, gear_context=None
):
    """Returns a list of files matching the criteria given."""
    log.info("Walk the hierarchy and find matching files...")
    my_walker = Walker(root)
    finder = FileFinder(
        intent=intent,
        measurement=measurement,
        features=features,
        gear_context=gear_context,
    )
    for container in my_walker.walk():
        finder.curate_container(container)

    # De-dupe
    ids = list(set([f.get("file_id") for f in finder.files]))
    final_list = []
    for f in finder.files:
        if f.get("file_id") in ids:
            final_list.append(f)
            ids.remove(f.get("file_id"))

    return final_list


def list_func_scans(root_container):
    """Search for all functional scans and return full file objects"""
    return get_matching_files(
        root_container, measurement="T2*", intent="Functional", features=["Task"]
    )


def list_sbref_scans(root_container):
    """Search for all SBRefs and return the full file object"""
    return get_matching_files(
        root_container, measurement="T2*", intent="Functional", features=["SBRef"]
    )

#!/usr/bin/env python3
"""."""

import logging

import pandas as pd

from .BIDSCuration import COLUMNS

log = logging.getLogger(__name__)


def get_bids_info(project, bc, subject_id=None, session_id=None):
    """Gather information to describe BIDS mapping.

    For each container and file name, get the full BIDS path, fieldmap IntendedFors
    and other information to be able to present the context so that proper bids
    information can be determined.

    Information is gathered here and saved into global variables.

    Args:
        project (Flywheel project object): the project to get BIDS curation info bout
        bc (BIDSCuration object): Instance of projuct curation report
        subject_id (str): Ignore all subjects that don't have this ID
        session_id (str): Ignore all sessions that don't have this ID

    Returns:
            num_subjects (int): number of subjects found
            num_sessions (int): number of sessions found
            num_duplicates (int): number of duplicates detected
    """

    num_subjects = 0
    num_sessions = 0
    num_duplicates = 0

    # Look through all acquisition files in the project and get their BIDS path
    for subject in project.subjects.iter_find():

        if subject_id:
            if subject.id != subject_id:
                continue

        num_subjects += 1

        log.debug(subject.label)

        # The number of times an acquisition with a given name is found for each subject
        bc.subjects_have[
            subject.label
        ] = dict()  # subjects_have[subject.label][acquisition.label] = count

        # Gather IntendedFor information here to be saved into a .csv file later.  Dictionary keys for all
        # of these is the session label and then acquisition file name.  Subject label will be added later for
        # the "all_intended_for..." dictionaries, like:  ["subject.label"]["session.label"]["field map file name"]
        intended_for_acq_label = dict()  # acquisition.label
        intended_for_acq_id = dict()  # acquisition.id
        # intended_for_dirs can be any or all of [{"Folder": "anat"}, {"Folder": "func"}, {"Folder": "dwi"}]
        intended_for_dirs = dict()
        # intended_fors are a list of paths [bids_relative_path1, bids_relative_path2, ...]
        intended_fors = dict()

        # bids_relative_path is, e.g., ses-01/func/sub-001_ses-01_task-rest_run-1_bold.nii.gz.  That is,
        # for a particular subject's field map, the path, including session, to the files the field map is
        # intended to be used on. See
        # https://bids-specification.readthedocs.io/en/v1.4.1/04-modality-specific-files/01-magnetic-resonance-imaging-data.html#fieldmap-data

        # Gather file information here for saving into a .csv file later
        nifti_df = pd.DataFrame(columns=COLUMNS)

        ii = 0  # Current acquisition file index

        seen_paths = (
            dict()
        )  # seen_paths[full_bids_path] = count (# of times this path has been found)

        for session in subject.sessions.iter_find():

            if session_id:
                if session.id != session_id:
                    continue

            num_sessions += 1

            session_ignored = ""
            if "BIDS" in session.info:
                session_ignored = "S" if session.info["BIDS"]["ignore"] else ""
            else:
                print(f"WARNING: 'BIDS' is missing in session '{session.label}'")

            for acquisition in session.acquisitions.iter_find():

                log.debug(f"{ii}  {acquisition.label}")

                if acquisition.label in bc.acquisition_labels:
                    bc.acquisition_labels[acquisition.label] += 1
                else:
                    bc.acquisition_labels[acquisition.label] = 1

                if acquisition.label in bc.subjects_have[subject.label]:
                    bc.subjects_have[subject.label][acquisition.label] += 1
                else:
                    bc.subjects_have[subject.label][acquisition.label] = 1

                acquisition_ignored = ""
                if "BIDS" in acquisition.info:
                    acquisition_ignored = (
                        "A" if acquisition.info["BIDS"]["ignore"] else ""
                    )
                else:
                    print(
                        f"WARNING: 'BIDS' is missing in acquisition '{acquisition.label}'"
                    )

                for file in acquisition.reload().files:

                    # determine full BIDS path
                    rule_id = ""
                    full_bids_path = ""  # /sub-.../ses-.../{Folder}/{Filename} for checking duplicates
                    if "BIDS" in file.info:
                        if file.info["BIDS"] == "NA":
                            bids_path = "unrecognized"
                            file_ignored = ""
                        else:
                            bids_path = ""
                            # check for craziness that should never happen
                            expected = ["ignore", "Folder", "Filename"]
                            for key in expected:
                                if key not in file.info["BIDS"]:
                                    bids_path += f"missing_{key} "
                            if bids_path == "":
                                bids_path = (
                                    f"{file.info['BIDS']['Folder']}/"
                                    + f"{file.info['BIDS']['Filename']}"
                                )
                                # The {file.info.BIDS.Path} always has the {file.info.BIDS.Folder} at the end
                                # for most BIDS formatted files.  This is not true for sourcedata (which is not
                                # BIDS formatted) and it is not true for files on containers because they are
                                # not in any of the BIDS "Folders" (anat, dwi, fmap, func).
                                full_bids_path = (
                                    f"{file.info['BIDS']['Path']}/"
                                    + f"{file.info['BIDS']['Filename']}"
                                )

                            file_ignored = (
                                "F" if file.info["BIDS"].get("ignore", "") else ""
                            )

                            rule_id = file.info["BIDS"].get("rule_id", "")

                        if (
                            "IntendedFor" in file.info
                            and len(file.info["IntendedFor"]) > 0
                        ):

                            # Add a "session.label" depth to these because different sessions can have the same
                            # field map file name more than once (but not usually)
                            if session.label not in intended_fors:
                                intended_fors[session.label] = dict()
                                intended_for_acq_label[session.label] = dict()
                                intended_for_acq_id[session.label] = dict()
                                intended_for_dirs[session.label] = dict()

                            intended_fors[session.label][file.name] = file.info[
                                "IntendedFor"
                            ]
                            intended_for_acq_label[session.label][
                                file.name
                            ] = acquisition.label
                            intended_for_acq_id[session.label][
                                file.name
                            ] = acquisition.id
                            if "IntendedFor" in file.info["BIDS"]:
                                intended_for_dirs[session.label][file.name] = file.info[
                                    "BIDS"
                                ]["IntendedFor"]
                            else:
                                # This only happens when a previous curation run had folder(s) here
                                # but this one does not.
                                intended_for_dirs[session.label][file.name] = [
                                    {"Folder": "folder is missing"}
                                ]
                                print(
                                    f"WARNING: {file.name} has no folders in file.info['BIDS']"
                                )
                    else:
                        bids_path = "Not_yet_BIDS_curated"
                        file_ignored = ""

                    if "SeriesNumber" in file.info:
                        series_number = file.info["SeriesNumber"]
                    else:
                        series_number = "?"

                    ignored = f"{session_ignored} {acquisition_ignored} {file_ignored}"

                    # Detect Duplicates
                    if ignored != "  ":  # if it IS ignored
                        unique = ""
                        bids_path = "ignored"  # don't show path to emphasize ignored
                    elif bids_path in ["unrecognized", "Not_yet_BIDS_curated"]:
                        unique = ""
                    elif full_bids_path != "":
                        if full_bids_path in seen_paths:
                            seen_paths[full_bids_path] += 1
                            unique = f"duplicate {seen_paths[full_bids_path]}"
                            num_duplicates += 1
                        else:
                            seen_paths[full_bids_path] = 0
                            unique = "unique"

                    log.debug(
                        f"{subject.label}, {session.label}, {series_number}, {ignored},"
                        f"{rule_id}, {acquisition.label}, {file.name}, {file.type}, "
                        f"{bids_path}, {unique}"
                    )

                    nifti_df.loc[ii] = [
                        subject.label,
                        session.label,
                        series_number,
                        ignored,
                        rule_id,
                        acquisition.label,
                        file.name,
                        file.type,
                        bids_path,
                        unique,
                    ]
                    ii += 1

        nifti_df.sort_values(by=["Curated BIDS path"], inplace=True)

        bc.all_df = pd.concat([bc.all_df, nifti_df])

        bc.all_intended_for_acq_label[subject.label] = intended_for_acq_label
        bc.all_intended_for_acq_id[subject.label] = intended_for_acq_id
        bc.all_intended_for_dirs[subject.label] = intended_for_dirs
        bc.all_intended_fors[subject.label] = intended_fors

        bc.all_seen_paths[subject.label] = seen_paths

    return num_subjects, num_sessions, num_duplicates

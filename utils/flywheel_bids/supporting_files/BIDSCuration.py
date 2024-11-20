import csv
import logging
import re
from ast import literal_eval

import pandas as pd

log = logging.getLogger(__name__)


def save_all_intended_fors(bc, intendedfors_writer, new=None):
    """Write all info about IntendedFors to csv file.

    The resulting csv file looks like:

        Initial values (before correction),
        acquisition label,                  file name and folder,   IntendedFor list of BIDS paths (fmap BIDS name)
        acq-label-1,                        acq-file-name-1,
                                            anat,
                                                                    ses-001/anat/sub-001_ses-001_T1w.nii.gz
                                                                    ses-001/anat/sub-001_ses-001_T2w.nii.gz
                                                                    ...
                                            func,
                                                                    ses-001/func/sub-001_ses-001_task-rest_bold.nii.gz
                                                                    ...
                                            ...
        Initial values (before correction),
        [repeat of above only filtered by regexes]

    Args:
        bc (BIDSCuration)
        intendedfors_writer (csv writer)
        new (bc.all_intended_fors) use this one if it is provided.  This function is called twice, once before
            editing the IntendedFors with the regexes and again afterwards.  The parameter "new" is the edited
            IntendedFors.
    """

    for subj_label in bc.all_intended_for_dirs:

        for session_label in bc.all_intended_for_dirs[subj_label]:

            for fmap_fname, folder_names in bc.all_intended_for_dirs[subj_label][
                session_label
            ].items():

                log.debug(
                    f"{bc.all_intended_for_acq_label[subj_label][session_label][fmap_fname]}, {fmap_fname}"
                )
                fmap_bids_name = bc.all_df.loc[
                    (bc.all_df["Subject"] == subj_label)
                    & (bc.all_df["Session"] == session_label)
                    & (bc.all_df["File name"] == fmap_fname),
                    "Curated BIDS path",
                ].tolist()[0]
                intendedfors_writer.writerow(
                    [
                        bc.all_intended_for_acq_label[subj_label][session_label][
                            fmap_fname
                        ],
                        fmap_fname,
                        fmap_bids_name,
                    ]
                )

                if isinstance(folder_names, str):
                    if folder_names != "":
                        folder_names = literal_eval(folder_names)

                for folder_name in folder_names:
                    log.debug(f",{folder_name['Folder']}")
                    intendedfors_writer.writerow([" ", folder_name["Folder"]])
                    bc.all_intended_fors[subj_label][session_label][fmap_fname].sort()

                    if new is None:
                        ifs_to_use = bc.all_intended_fors
                    else:
                        ifs_to_use = new

                    for intended_for in ifs_to_use[subj_label][session_label][
                        fmap_fname
                    ]:
                        what_to_find = f"/{folder_name['Folder']}/"
                        if what_to_find in intended_for:
                            log.debug(f",,{intended_for}")
                            intendedfors_writer.writerow([" ", " ", intended_for])


def filter_intended_fors(fw, bc, intended_for_regexes):
    """Use pairs of regexes to match field maps with the files they modify.

    In the earlier part of curation, curate_bids() (the project curation template engine)
    sets a field map's file.info.IntendedFor to be a list of ALL FILES in the folders
    specified by that field map's file.info.BIDS.IntendedFor (a list of folders: anat, dwi, func).
    This function takes that list of files and only keeps the proper ones.

    The first regular expression in each pair matches the field map name, and the
    second regex matches the IntendedFor (relative path to file).  IntendedFors are
    kept only when both regexes match.

    The main effect of this function is to modify the field map's file.info.IntendedFor metadata.
    It returns the filtered list so that it can be printed.

    Args:
        fw (Flywheel Client)
        bc (BIDSCuration)
        intended_for_regexes (str): pairs of regular expressions

    Returns:
        new_intended_fors (list of strings): for each field map, list of paths to files it modifies
    """

    ifr = intended_for_regexes.split(" ")
    if len(ifr) % 2:
        raise Exception(
            f"{ifr} has an odd number of regexes.  The space-separated list of regexes must contain pairs."
        )
    string_pairs = zip(ifr[::2], ifr[1::2])
    # for pair in string_pairs:
    #    print(f"fmap regex \"{pair[0]}\" will correct file \"{pair[1]}\"")

    regex_pairs = list()
    for s_p in string_pairs:
        regex_pairs.append([re.compile(s_p[0]), re.compile(s_p[1])])

    new_intended_fors = dict()

    for subj_label in bc.all_intended_fors:

        new_intended_fors[subj_label] = dict()

        for session_label in bc.all_intended_fors[subj_label]:

            new_intended_fors[subj_label][session_label] = dict()

            for fmap_fname, acquisition_label in bc.all_intended_for_acq_label[
                subj_label
            ][session_label].items():
                log.debug(f"{acquisition_label}")

                for regex in regex_pairs:

                    if regex[0].search(acquisition_label):

                        new_intended_fors[subj_label][session_label][
                            fmap_fname
                        ] = list()

                        for i_f in bc.all_intended_fors[subj_label][session_label][
                            fmap_fname
                        ]:
                            if regex[1].search(i_f):
                                log.debug(f"found {i_f}")
                                new_intended_fors[subj_label][session_label][
                                    fmap_fname
                                ].append(i_f)

                        fw.modify_acquisition_file_info(
                            bc.all_intended_for_acq_id[subj_label][session_label][
                                fmap_fname
                            ],
                            fmap_fname,
                            {
                                "set": {
                                    "IntendedFor": new_intended_fors[subj_label][
                                        session_label
                                    ][fmap_fname]
                                }
                            },
                        )

    return new_intended_fors


def get_most_subjects_count(acquisition_labels, subjects_have):
    """For each acquisition label find the number of times it appears across subjects.

    This produces a histogram of the number of times an acquisition appears across subjects.  It is used to
    calculate self.most_subjects_have, which is the number of times an acquisition appears for most subjects.

    There has to be a better way of doing this.

    Args:
        acquisition_labels (dict) # acquisition_labels[acquisition.label] = count over entire project
        subjects_have (dict) subjects_have[subject.label][acquisition.label] = count
    Returns:
        most_subjects_have_count (dict) most_subjects_have_count[acquisition.label][count] a count histogram
    """

    most_subjects_have_count = dict()

    # and all acquisition labels found in any subject
    for acq_label in acquisition_labels:

        # create the "histogram"
        if acq_label not in most_subjects_have_count:
            most_subjects_have_count[acq_label] = dict()

        # go through all subjects
        for subj_label in subjects_have:

            if acq_label in subjects_have[subj_label]:

                # the number of times an acquisition label appears for each subject
                count = subjects_have[subj_label][acq_label]

                if count in most_subjects_have_count[acq_label]:
                    most_subjects_have_count[acq_label][count] += 1
                else:
                    most_subjects_have_count[acq_label][count] = 1

            else:  # label not seen for subject so count # of times it was missing
                if 0 in most_subjects_have_count[acq_label]:
                    most_subjects_have_count[acq_label][0] += 1
                else:
                    most_subjects_have_count[acq_label][0] = 1

    return most_subjects_have_count


# This is used to create the main "_niftis.csv" report that lists every bids path
COLUMNS = (
    "Subject",
    "Session",
    "SeriesNumber",
    "Ignored",
    "Rule ID",
    "Acquisition label (SeriesDescription)",
    "File name",
    "File type",
    "Curated BIDS path",
    "Unique?",
)


class BIDSCuration:
    """Representation of Flywheel metadata BIDS Curation."""

    def __init__(self):
        self.all_df = pd.DataFrame(columns=COLUMNS)

        # Counts of all unique acquisition labels
        # acquisition_labels[acquisition.label] = count over entire project
        self.acquisition_labels = dict()

        # subjects_have[subject.label][acquisition.label] = count for this subject
        self.subjects_have = dict()

        # most_subjects_have is the number times that an acquisition label appears for most subjects.
        # This is set in save_acquisition_details() below. It is a list:
        #   most_subjects_have[acquisition label] = [list of counts]
        self.most_subjects_have = dict()
        self.most_subjects_have_str = dict()  # for printing

        # Dictionary keys for all of these are:  ["subject.label"]["session.label"]["field map file name"]
        self.all_intended_for_acq_label = dict()  # field map acquisition.label
        self.all_intended_for_acq_id = (
            dict()
        )  # field map acquisition.id used for updating IntendedFor list
        # intended_for_dirs can be any or all of [{"Folder": "anat"}, {"Folder": "func"}, {"Folder": "dwi"}]
        self.all_intended_for_dirs = dict()
        # intended_fors are a list of paths [bids_relative_path1, bids_relative_path2, ...]
        self.all_intended_fors = dict()

        # all_seen_paths[bids_path] = count     This is used to detect duplicates
        self.all_seen_paths = dict()

    def save_niftis(self, pre_path):
        """Save acquisition/file name -> bids path mapping.

        Args:
            pre_path (str) "group-name_project-name"
        """

        self.all_df.to_csv(f"{pre_path}_niftis.csv", index=False)

    def save_intendedfors(self, pre_path, intended_for_regexes, fw):
        """save field map IntendedFor lists.

        If intended_for_regexes has been provided, this method will only keep the ones that match
        The others will be removed from the field map's IntendedFor metadata, file.info.IntendedFor

        Args:
            pre_path (str) "group-name_project-name"
            intended_for_regexes (str) a list of regex pairs
        """

        with open(f"{pre_path}_intendedfors.csv", mode="w") as intendedfors_file:
            intendedfors_writer = csv.writer(
                intendedfors_file,
                delimiter=",",
                quotechar='"',
                quoting=csv.QUOTE_MINIMAL,
            )

            intendedfors_writer.writerow(
                [
                    "acquisition label",
                    "file name and folder",
                    "IntendedFors: List of relative BIDS paths (fmap BIDS name)",
                ]
            )

            save_all_intended_fors(self, intendedfors_writer)

            # Keep only proper file paths if they match field maps as per provided regexes
            if intended_for_regexes:

                new_intended_fors = filter_intended_fors(fw, self, intended_for_regexes)

                intendedfors_writer.writerow(
                    ["Final values (after correction using regexes)"]
                )

                # write out final values of IntendedFor lists
                intendedfors_writer.writerow(
                    [
                        " ",
                        " ",
                        " ",
                    ]
                )
                intendedfors_writer.writerow(
                    [
                        "acquisition label",
                        "file name and folder",
                        "IntendedFor List of BIDS paths",
                    ]
                )

                # Write out intended_fors again since they were filtered
                save_all_intended_fors(self, intendedfors_writer, new=new_intended_fors)

    def save_acquisition_details(self, num_subjects, num_sessions, pre_path):
        """Save acquisition labels count list.

        This saves two spreadsheets

        NOTE: self.most_subjects_have and self.most_subject_have_str are set in this method.
        The first is a list of numbers and the second is a string that is used for printing.
        This can list multiple counts because multiple acquisition counts could be present at the
        maximum bin of the histogram of counts.  For example if most_subjects_have_count (see get_most_subjects_count)
        is "Localizer": {6: 2, 5: 2}, it means that Localizer appears 6 times for 2 subjects and 5 times,
        also for 2 subjects.  So the max of the histogram is 2 and there are two possibilities for the counts
        (6 and 5).  Usually, most_subjects_have_count has something like "BOLD_taxi2": {5: 3, 6: 1}, where the
        BOLD_taxi2 acquisition for 3 subjects is found 5 times but in 1 subject it was found 6 times.  So 5 is
        the number of appearances that most subjects have.  This only saves the counts for the maximum histogram
        bin.  Depending on the shape of the histogram it might be better to keep the counts for the top few bins.
        This determines what is meant by "most" in the "number of scans that MOST subjects have".

        Why does an acquisition label appear multiple times when they should be unique so that the BIDS names are
        unique?  Because mistakes happen in scanning and in setting up BIDS curation and this spreadsheet is to
        help figure out what is going on.

        Args:
            num_subjects (int) total number of subject
            num_sessions (int) total number of sessions in project
            pre_path (str) "group-name_project-name"
        """

        with open(
            f"{pre_path}_acquisitions_details_1.csv", mode="w"
        ) as acquisition_file:
            acquisition_writer = csv.writer(
                acquisition_file,
                delimiter=",",
                quotechar='"',
                quoting=csv.QUOTE_MINIMAL,
            )

            acquisition_writer.writerow(["Number of subjects", num_subjects])
            acquisition_writer.writerow(["Number of sessions", num_sessions])
            acquisition_writer.writerow([])

            acquisition_writer.writerow(
                ["Unique acquisition label", "total number found"]
            )
            for label, count in self.acquisition_labels.items():
                acquisition_writer.writerow([label, count])

            acquisition_writer.writerow([])
            acquisition_writer.writerow(["Acquisition label", "Usual count"])

            most_subjects_have_count = get_most_subjects_count(
                self.acquisition_labels, self.subjects_have
            )

            # the max of the counts for an acquisition label is the number of that acquisition that most subjects have
            for acq_label in self.acquisition_labels:
                max_count = 0
                max_index = 0
                for count, num_count in most_subjects_have_count[acq_label].items():
                    if num_count > max_count:
                        max_count = num_count
                        max_index = count

                # see if the max is repeated
                most_counts = []
                for count, num_count in most_subjects_have_count[acq_label].items():
                    if num_count == max_count:
                        most_counts.append(count)

                if len(most_counts) > 1:
                    result = " or ".join([str(int) for int in most_counts])
                else:
                    result = str(max_index)

                self.most_subjects_have[
                    acq_label
                ] = most_counts  # see discussion above for definition of "most"
                self.most_subjects_have_str[acq_label] = result

                acquisition_writer.writerow([acq_label, result])

        with open(
            f"{pre_path}_acquisitions_details_2.csv", mode="w"
        ) as acquisition_file:
            acquisition_writer = csv.writer(
                acquisition_file,
                delimiter=",",
                quotechar='"',
                quoting=csv.QUOTE_MINIMAL,
            )
            acquisition_writer.writerow(
                ["Subject", "Acquisition", "Count != to", "Usual count"]
            )

            for subj_label in self.subjects_have:
                found_problem = False
                acquisition_writer.writerow([subj_label])
                for acq_label in self.acquisition_labels:
                    if acq_label in self.subjects_have[subj_label]:
                        if (
                            self.subjects_have[subj_label][acq_label]
                            not in self.most_subjects_have[acq_label]
                        ):
                            found_problem = True  # doesn't have what most subjects have
                            acquisition_writer.writerow(
                                [
                                    " ",
                                    acq_label,
                                    self.subjects_have[subj_label][acq_label],
                                    self.most_subjects_have_str[acq_label],
                                ]
                            )
                    else:
                        if 0 not in self.most_subjects_have[acq_label]:
                            found_problem = True  #  This acquisiton is missing for this subject and most have some
                            acquisition_writer.writerow(
                                [
                                    " ",
                                    acq_label,
                                    0,
                                    self.most_subjects_have_str[acq_label],
                                ]
                            )
                if not found_problem:
                    acquisition_writer.writerow(
                        [
                            " ",
                            "Subject has all of the usual acquisitions, no  more, no less!",
                        ]
                    )

    def save_acquisitions(self, pre_path):
        """Save typical acquisitions and lists of good/bad subjects.

        This must be called AFTER save_acquisition_details() because
            that sets the typical number of acquisitions

        Args:
            pre_path (str) "group-name_project-name"
        """

        with open(f"{pre_path}_acquisitions.csv", mode="w") as acquisition_file:
            acquisition_writer = csv.writer(
                acquisition_file,
                delimiter=",",
                quotechar='"',
                quoting=csv.QUOTE_MINIMAL,
            )

            acquisition_writer.writerow(["Acquisition Label", "Usual Count"])
            for acq_label, usual_count in self.most_subjects_have.items():
                if usual_count[0] > 0:
                    acquisition_writer.writerow(
                        [acq_label, self.most_subjects_have_str[acq_label]]
                    )

            acquisition_writer.writerow([])
            acquisition_writer.writerow(
                ["Subjects that have all of the Typical Acquisitions"]
            )
            troubled_subjects = dict()
            has_no_errors = list()
            for subj_label in self.subjects_have:
                no_errors = True
                warnings = False
                troubled_subjects[subj_label] = list()
                for acq_label, usual_count in self.most_subjects_have.items():
                    if acq_label not in self.subjects_have[subj_label]:
                        if usual_count[0] > 0:
                            no_errors = False
                            troubled_subjects[subj_label].append(
                                f"ERROR: missing {acq_label}"
                            )
                    else:
                        subj_has = self.subjects_have[subj_label][acq_label]
                        most_have = self.most_subjects_have[acq_label]
                        most_have_str = self.most_subjects_have_str[acq_label]
                        if subj_has < min(most_have):
                            no_errors = False
                            troubled_subjects[subj_label].append(
                                f"ERROR: not enough {acq_label} acquisitions.  Found {subj_has}, most have {most_have_str}"
                            )
                        elif subj_has > max(most_have):
                            warnings = True
                            if usual_count[0] > 0:
                                troubled_subjects[subj_label].append(
                                    f"WARNING: too many {acq_label} acquisitions?  Found {subj_has}, most have {most_have_str}"
                                )
                            else:
                                troubled_subjects[subj_label].append(
                                    f"WARNING: extra {acq_label} acquisition(s)?  Found {subj_has}, most subjects don't have this."
                                )
                if no_errors:
                    has_no_errors.append(subj_label)
                    acquisition_writer.writerow([subj_label])
                    if warnings:
                        for warning in troubled_subjects[subj_label]:
                            acquisition_writer.writerow([" ", warning])
                    else:
                        acquisition_writer.writerow(
                            [
                                " ",
                                "This subject has all of the typical acquisitions, no more, no less.",
                            ]
                        )

            acquisition_writer.writerow([])
            acquisition_writer.writerow(
                ["Subjects that don't have Typical Acquisitions"]
            )
            for subj_label, bad_news in troubled_subjects.items():
                if subj_label in has_no_errors:
                    pass
                else:
                    acquisition_writer.writerow([subj_label])
                    for news in bad_news:
                        acquisition_writer.writerow([" ", news])

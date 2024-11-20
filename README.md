# QSIRecon Gear

This gear runs [QSIRecon](https://qsirecon.readthedocs.io/en/latest/index.html) on
[BIDS-curated data](https://bids.neuroimaging.io/).

For a description of what QSIrecon does, read the
[official documentation](https://qsirecon.readthedocs.io/en/latest/index.html).  

This gear runs the official
[`pennlinc/qsirecon:0.23.2` Docker image](https://hub.docker.com/r/pennlinc/qsirecon/tags)

## Overview

[Usage](#usage)

[FAQ](#faq)

### Summary

`qsirecon` builds post-processing workflows that produce many of the biologically-interesting dMRI derivatives used for hypothesis testing. QSIrecon builds on qsiprep (an accompyanying preprocessing workflow for dMRI data), however data is not required to be preprocessed with this package. Fro more information see QSIrecon [official documentation](https://qsirecon.readthedocs.io/en/latest/index.html).

### Cite

**license:** <https://qsirecon.readthedocs.io/en/latest/license.html>

* Dependencies:
  * FSL: <https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/Licence>
  * ANTs: <https://github.com/ANTsX/ANTs/blob/v2.2.0/COPYING.txt>
  * AFNI: <https://afni.nimh.nih.gov/pub/dist/doc/program_help/README.copyright.html>
  * DSI-Studio: <https://dsi-studio.labsolver.org/download.html>
  * MRtrix3: <https://github.com/MRtrix3/mrtrix3/blob/master/LICENCE.txt>

### Classification

*Category:* analysis

*Gear Level:*

* [ ] Project
* [x] Subject
* [x] Session
* [ ] Acquisition
* [ ] Analysis

----

[[*TOC*]]

----

### Inputs

* bidsignore
  * **Name**: bidsignore
  * **Type**: object
  * **Optional**: true
  * **Classification**: file
  * **Description**: A .bidsignore file to provide to the bids-validator that this gear
runs before running the main command.

* freesurfer_license_file
  * **Name**: freesurfer_license_file
  * **Type**: object
  * **Optional**: true
  * **Classification**: file
  * **Description**: FreeSurfer license file, provided during registration with
FreeSurfer. This file will be copied to the `$FSHOME` directory and used during
execution of the Gear.

* preprocessing_pipeline
  * **Name**: preprocessing_pipeline
  * **Type**: object
  * **Optional**: false
  * **Classification**: file
  * **Description**: Zipped output from preprocessing dMRI pipeline. Example pipelines: qsiprep, uk biobank, HCP young adult. Should be properly matched with appropriate config flag `input-type`.
  * 
* api-key
  * **Name**: api-key
  * **Type**: object
  * **Optional**: true
  * **Classification**: api-key
  * **Description**: Flywheel API key.

* recon-spec
  * **Name**: recon-spec
  * **Type**: object
  * **Optional**: true
  * **Classification**: file
  * **Description**: json file specifying a reconstruction pipeline to be run after preprocessing.

### Config

* debug
  * **Name**: debug
  * **Type**: boolean
  * **Description**: Log debug messages
  * **Default**: false

* bids_app_args
  * **Name**: bids_app_args
  * **Type**: string
  * **Description**: Extra arguments to pass to the BIDS App, space-separated:
`[arg1 [arg2 ...]]`
  * **Default**: "" (empty)

* interactive-reports-only
  * **Name**: interactive-reports-only
  * **Type**: boolean
  * **Description**: create interactive report json files on already preprocessed data.
  * **Optional**: true

* verbose
  * **Name**: verbose
  * **Type**: string
  * **Description**: increases log verbosity for each occurrence, debug level is `-vvv`
  * **Optional**: true

* n_cpus
  * **Name**: n_cpus
  * **Type**: integer
  * **Description**: Number of CPUs/cores to use. Leave blank or set to `0` to use the
maximum available in the system.
  * **Optional**: true

* mem_mb
  * **Name**: mem_mb
  * **Type**: integer
  * **Description**: Maximum memory to use (MB). Leave blank or set to 0 to use the
maximum available in the system.
  * **Optional**: true

* gear-save-intermediate-output
  * **Name**: gear-save-intermediate-output
  * **Type**: boolean
  * **Description**: Gear will save ALL intermediate output into `qsirecon_work.zip`.
  * **Optional**: true

* gear-intermediate-files
  * **Name**: gear-intermediate-files
  * **Type**: string
  * **Description**: Space separated list of FILES to retain from the intermediate work
directory.
  * **Optional**: true

* gear-intermediate-folders
  * **Name**: gear-intermediate-folders
  * **Type**: boolean
  * **Description**: Space separated list of FOLDERS to retain from the intermediate work
directory.
  * **Optional**: true

* gear-dry-run
  * **Name**: gear-dry-run
  * **Type**: boolean
  * **Description**: Do everything except actually executing `qsirecon`.
  * **Optional**: true

* gear-keep-output
  * **Name**: gear-keep-output
  * **Type**: boolean
  * **Description**: Don't delete output.  Output is always zipped into a single file
for easy download.  Choose this option to prevent output deletion after zipping.
  * **Optional**: true

* gear-FREESURFER_LICENSE
  * **Name**: gear-FREESURFER_LICENSE
  * **Type**: string
  * **Description**: Text from license file generated during FreeSurfer registration.
*Entries should be space separated*.
  * **Optional**: true

### Outputs

Please refer to the [official documentation](https://qsirecon.readthedocs.io/)

#### Metadata

Any notes on metadata created by this gear

### Pre-requisites

This section contains any prerequisites

#### Prerequisite Gear Runs

This gear runs on dMRI preprocessed data. Data must be preprocessed using appropriate dMRI gear before this pipeline can be executed. Currently availible preprocessing gears: [bids-qsiprep](https://github.com/intermountainneuroimaging/bids-qsiprep). 

#### Prerequisite

This BIDS-App runs FreeSurfer, so you need to provide a valid FreeSurfer license.

Supported ways to provide the license are documented [here](
https://docs.flywheel.io/hc/en-us/articles/360013235453)

## Usage

This section provides a more detailed description of the gear, including not just WHAT
it does, but HOW it works in flywheel

### Description

This gear is run at either the `Subject` or the `Session` level. 

After the pipeline is run, the output folder is zipped and saved into the analysis
container.

#### File Specifications

This section contains specifications on any input files that the gear may need

### Use Cases

Please, refer to the [official documentation](https://qsirecon.readthedocs.io/)

## FAQ

[FAQ.md](FAQ.md)

## Contributing

[For more information about how to get started contributing to that gear,
checkout [CONTRIBUTING.md](CONTRIBUTING.md).]

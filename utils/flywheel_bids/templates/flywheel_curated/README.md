# Flywheel Engineer Curated Project Curation JSON Templates

The structure of the Project Curation JSON Templates in this directory must follow the
following filename convention:

```markdown
\<project-site>-\<project-name>-\<secondary-identifying-term>-project-template.json
```

Where:

`\<project-site>`: the site for the project, typically the name of the Flywheel instance.

`\<project-name>`: the name for the project.

`\<secondary-identifying-term>`: dealers choice; typically indicates the type of the
template, such as reproin or extension, or indicates a particular study within a project.

For example, the filename _bridge-headspace-extension-project-template.json_ is an
extension Project Curation JSON Template for the Headspace project at the CMU-Pitt
BRIDGE Center.

Accompanying the Project Curation JSON Template is an attributes text file that
contains important information about the template that helps to inform the user of the
intended usage. The filename convention for these files must be the same basename as
the Project Curation JSON Template, appended with _attributes_, and use the _.txt_ file
extension:

```markdown
\<project-site>-\<project-name>-\<secondary-identifying-term>-project-template-attributes.txt
```

The contents of the template attributes file should include the BIDS specification
version used, a description of the type of study the template aims to curate, when the
template was last modified, and any other information that may be relevant for another
user to interpret the template.

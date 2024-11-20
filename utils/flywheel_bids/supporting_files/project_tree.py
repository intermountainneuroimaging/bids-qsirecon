import collections
import copy
import logging

from rtstatlib import rtstat

if __name__ == "__main__":
    import utils
else:
    from . import utils

logger = logging.getLogger("curate-bids")


class TreeNode(collections.abc.MutableMapping):
    """
    Represents a single node (Project, Session, Acquisition or File) in
    the Flywheel hierarchy.

    Args:
        node_type (str): The type of node (lowercase)
        data (dict): The node data

    Attributes:
        type: The type of node
        data: The node data
        children: The children belonging to this node
        original_info: The original value of the 'info' property
    """

    def __init__(self, node_type, data):
        self.type = node_type
        self.data = data
        self.children = []

        # save a copy of original info object so we know when
        # we need to do an update
        self.original_info = copy.deepcopy(self.data.get("info"))

    def is_dirty(self):
        """
        Check if 'info' attribute has been modified.

        Returns:
            bool: True if info has been modified, False if it is unchanged
        """
        info = self.data.get("info")
        return info != self.original_info

    def to_json(self):
        return {
            "type": self.type,
            "data": self.data,
            "children": [x.to_json() for x in self.children],
        }

    @staticmethod
    def from_json(cls, data):
        node = TreeNode(data["type"], data["data"])
        for child in data.get("children", []):
            node.children.append(TreeNode.from_json(child))
        return node

    def context_iter(self, context=None):
        """
        Iterate the tree depth-first, producing a context for each node.

        Args:
            context (dict): The parent context object

        Yields:
            dict: The context object for this node
        """
        if not context:
            context = {"parent_container_type": None}

        # Depth-first walk down tree
        context["container_type"] = self.type
        context[self.type] = self

        # Bring subject to top-level of context
        if self.type == "session":
            context["subject"] = self.data["subject"]

        # Additionally bring ext up if file
        if self.type == "file":
            context["ext"] = utils.get_extension(self.data["name"])

        # Yield the current context before processing children
        yield context

        context["parent_container_type"] = self.type
        for child in self.children:
            context_copy = context.copy()
            for ctx in child.context_iter(context_copy):
                yield ctx

    def __len__(self):
        return len(self.data)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, item):
        self.data[key] = item

    def __delitem__(self, key):
        del self.data[key]

    def __iter__(self):
        return iter(self.data)

    def __contains__(self, key):
        return key in self.data

    def __repr__(self):
        return repr(self.data)


def add_file_nodes(parent):
    """
    Add file nodes as children to parent.

    Args:
        parent (TreeNode): The parent node
    """

    if parent.type == "project":
        dnt = ""
    elif parent.type == "session":
        dnt = "\t\t"
    elif parent.type == "acquisition":
        dnt = "\t\t\t\t"

    logger.debug(f"{dnt}{parent.type}: {parent.data['label']}")

    for f in parent.get("files", []):
        parent.children.append(TreeNode("file", f))
        logger.debug(f"{dnt}\t'file': {f['name']}")


def get_project_node(fw, project_id):
    """Get the initial project node for the context tree.

    Args:
        fw (Flywheel client)
        project_id (str): hexadecimal string that identifies a particular project
    Returns:
    TreeNode: The project (root) tree node
    """

    # Get project
    logger.info("Getting project...")
    project_data = to_dict(fw, fw.get_project(project_id))
    project_node = TreeNode("project", project_data)
    add_file_nodes(project_node)

    rtstat.sync_log()

    return project_node


def set_tree(fw, project_node, subject, session_id=None):
    """
    Construct a project tree from the given project_id for the given subject (or session)

    Args:
        fw: Flywheel client
        subject (Flywheel subject container): the subject to curate
        session_id (str): Optional session_id if only single session is to be curated

    Returns: (nothing, but it adds children to the project_node)
    """
    if session_id:
        logger.info("Getting single session ID=%s", session_id)
    else:
        logger.info("Getting all sessions")

    for session in subject.sessions.iter():
        if session_id and session_id != session.id:
            continue

        session_data = to_dict(fw, session)
        session_node = TreeNode("session", session_data)
        add_file_nodes(session_node)

        project_node.children.append(session_node)

        session_acqs = session.acquisitions()
        for ses_acq in sorted(session_acqs, key=AcquisitionSortKey):
            # Get true acquisition, in order to access file info
            acquisition_data = to_dict(fw, fw.get_acquisition(ses_acq["_id"]))
            acquisition_node = TreeNode("acquisition", acquisition_data)
            add_file_nodes(acquisition_node)

            session_node.children.append(acquisition_node)


class AcquisitionSortKey(object):
    def __init__(self, acq, **args):
        self.acq = acq

    def __lt__(self, other):
        return self._cmp(other) < 0

    def __gt__(self, other):
        return self._cmp(other) > 0

    def __eq__(self, other):
        return self._cmp(other) == 0

    def __le__(self, other):
        return self._cmp(other) <= 0

    def __ge__(self, other):
        return self._cmp(other) >= 0

    def __ne__(self, other):
        return self._cmp(other) != 0

    def _cmp(self, other):
        ts1 = self.acq.get("timestamp")
        ts2 = other.acq.get("timestamp")
        if ts1 and ts2:
            return int((ts1 - ts2).total_seconds())
        return int((self.acq["created"] - other.acq["created"]).total_seconds())


def to_dict(fw, obj):
    return fw.api_client.sanitize_for_serialization(obj.to_dict())


if __name__ == "__main__":
    import argparse
    import json

    import flywheel

    parser = argparse.ArgumentParser(description="Dump project tree to json")
    parser.add_argument(
        "--api-key", dest="api_key", action="store", required=True, help="API key"
    )
    parser.add_argument(
        "-p",
        dest="project_label",
        action="store",
        required=False,
        default=None,
        help="Project Label on Flywheel instance",
    )
    parser.add_argument("output_file", help="The output file destination")

    args = parser.parse_args()

    fw = flywheel.Client(args.api_key)

    project_id = utils.validate_project_label(fw, args.project_label)

    project = fw.get_project(project_id)

    project_node = get_project_node(fw, project_id)

    for subject in project.subjects.iter():

        set_tree(fw, project_node, subject, session_id=None)

    with open(args.output_file, "w") as f:
        json.dump(project_node.to_json(), f, indent=2)

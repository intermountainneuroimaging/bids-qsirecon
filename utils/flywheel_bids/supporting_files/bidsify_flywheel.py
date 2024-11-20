import logging

from . import classifications, templates, utils

logger = logging.getLogger("curate-bids")


def determine_enum(theproperty, key, classification):
    """

    obj:  {'Task': '', 'Run': '', 'Filename': '', 'Acq': '', 'Rec': '', 'Path': '', 'Folder': 'func', 'Echo': ''}
    property: {'default': 'bold', 'enum': ['bold', 'sbref', 'stim', 'physio'], 'type': 'string', 'label': 'Modality Label'}
    classification:  {u'Intent': u'Functional'}

    """
    # Use the default value
    enum_value = theproperty.get("default", "")
    # If the default value is '', try and determine if from 'enum' list
    if not enum_value:
        # If key is modality, iterate over classifications dict
        if key == "Modality":
            for data_type in classifications.classifications.keys():
                # Loops through the enum values in the propdef, allows for prioritization
                for enum_value in theproperty.get("enum", []):
                    enum_req = classifications.classifications[data_type].get(
                        enum_value
                    )
                    if enum_req and utils.dict_match(enum_req, classification):
                        return enum_value

    return enum_value


# add_properties(properties, obj, measurements)
# Populates obj with properties defined in a namespace template
# Adds each key in the properties list and sets the value to the value specified in 'default' attribute
# Properties may be of type string or object. Will add other types later.
# Measurements passed through function so that Modality value can be determined


def add_properties(properties, obj, classification):
    for key in properties:
        proptype = properties[key]["type"]
        if proptype == "string":
            # If 'enum' in properties, seek to determine the value from enum list
            if "enum" in properties[key]:
                obj[key] = determine_enum(properties[key], key, classification)
            elif "default" in properties[key]:
                obj[key] = properties[key]["default"]
            else:
                obj[key] = "default"
        elif proptype == "object":
            obj[key] = properties[key].get("default", {})
        elif "default" in properties[key]:
            obj[key] = properties[key]["default"]
    return obj


# update_properties(properties, context, obj)
# Updates object values for items in properties list containing an 'auto_update' attribute.
# 'auto_update' may be specified using a string template containing tags to be replaced from value in 'context' object
# See process_string_template for details on how to use string templates
# Updated keys are added to the obj object for later update to Flywheel

# 'auto_update' can also be a dictionary with keys '$value' and '$format' that
# will use util.format_value, the value is a direct dict_lookup, the string
# is not processed


def update_properties(properties, context, obj):
    for key in properties:
        proptype = properties[key]["type"]
        if proptype == "string":
            if "auto_update" in properties[key]:
                auto_update = properties[key]["auto_update"]
                if isinstance(auto_update, dict):
                    if auto_update.get("$process"):
                        value = utils.process_string_template(
                            auto_update["$value"], context
                        )
                    else:
                        value = utils.dict_lookup(context, auto_update["$value"])
                    obj[key] = utils.format_value(auto_update["$format"], value)
                else:
                    obj[key] = utils.process_string_template(auto_update, context)

                logger.debug(f"Setting <{key}> to <{obj[key]}>")

    return obj


# process_matching_templates(context, template)
# Accepts a context object that represents a Flywheel container and related parent containers
# and looks for matching templates in namespace.
# Matching templates define rules for adding objects to the container's info object if they don't already exist
# Matching templates with 'auto_update' rules will update existing info object values each time it is run.


def process_matching_templates(
    context, template=templates.DEFAULT_TEMPLATE, upload=False
):
    debug_log = ""
    info_log = ""
    namespace = template.namespace

    container_type = context["container_type"]
    container = context[container_type]

    initial = (
        ("info" not in container)
        or (namespace not in container["info"])
        or ("template" not in container["info"][namespace])
    )

    templateDef = None
    if container.get("info", {}).get(namespace) == "NA":
        logger.debug(f"info.{namespace} is empty or NA")
        return container

    # add objects based on template if they don't already exist
    if initial:

        debug_log += (
            f"'info' not in container OR "
            f"{namespace} not in 'info' OR "
            f"'container template' not in info.{namespace}.  "
            f"Performing initial rule matching\n\n"
        )

        # Do initial rule matching
        match = False
        rules = template.rules
        # If matching on upload, test against upload_rules as well
        if upload:
            debug_log += "Matching on upload, testing against upload_rules\n\n"
            rules = rules + template.upload_rules
        for rule in rules:
            debug_log += f"checking rule: <{rule.id}> for container template: <{rule.template}>\n\n"
            if rule.test(context):
                debug_log += f"Match for rule {rule.id}\n\n"
                if container_type == "file":
                    what = container.get("name", "")
                else:
                    what = container.get("label", "")
                if rule.id:
                    rule_id = rule.id
                else:
                    rule_id = ""
                info_log += (
                    f"{what} matches container template {rule.template} {rule_id}\n\n"
                )
                match = True
                templateDef = template.definitions.get(rule.template)
                if templateDef is None:
                    raise Exception(
                        "Unknown container template: {0}".format(rule.template)
                    )

                if "info" not in container:
                    container["info"] = {}

                obj = container["info"].get(namespace, {})
                obj["template"] = rule.template
                obj["rule_id"] = rule.id
                container["info"][namespace] = add_properties(
                    templateDef["properties"], obj, container.get("classification")
                )
                if container_type in ["session", "acquisition", "file"]:
                    obj["ignore"] = False
                rule.initializeProperties(obj, context)
                if rule.id:
                    template.apply_custom_initialization(rule.id, obj, context)
                initial = False
                break
        if not match:
            if container_type == "file":
                label = container["name"]
            else:
                label = container["label"]
            debug_log = (
                f"rule {rule.conditions} not matched for {label} in "
                f"{context['parent_container_type']} "
                f"{context[context['parent_container_type']]['id']}\n\n"
            )
            info_log = ""

        logger.debug(debug_log)
        if info_log:
            logger.debug(info_log)

    if not initial:
        # Do auto_updates
        if not templateDef:
            templateDef = template.definitions.get(
                container["info"][template.namespace]["template"]
            )

        if templateDef:
            data = update_properties(templateDef["properties"], context, {})
            container["info"][namespace].update(data)

    return container


def process_resolvers(context, template=templates.DEFAULT_TEMPLATE):
    """
    Perform second stage path resolution based on template rules

    Args:
        session (TreeNode): The session node to search within
        context (dict): The context to perform path resolution on
        template (Template): The template
    """
    namespace = template.namespace

    container_type = context["container_type"]
    container = context[container_type]

    if (
        ("info" not in container)
        or (namespace not in container["info"])
        or ("template" not in container["info"][namespace])
    ):
        return

    # Determine the applied template name
    template_name = container["info"][namespace]["template"]
    # Get a list of resolvers that apply to this template
    resolvers = template.resolver_map.get(template_name, [])

    # Apply each resolver
    for resolver in resolvers:
        resolver.resolve(context)


def ensure_info_exists(context, template=templates.DEFAULT_TEMPLATE):
    """
    Ensure that the given info object has an entry for the template namespace.

    Args:
        context (dict): The context that should have a valid info object
        template (Template): The template

    Returns:
        bool: Whether or not the info was updated.
    """
    updated = False
    if "info" not in context:
        context["info"] = {}
        updated = True
    if template.namespace not in context["info"]:
        context["info"][template.namespace] = {}
        updated = True

    return updated

import json
import logging
import operator
import os
import os.path
import re

import jsonschema
import six

from . import resolver, utils

DEFAULT_TEMPLATE_NAME = "default"
BIDS_V1_TEMPLATE_NAME = "bids-v1"
REPROIN_TEMPLATE_NAME = "reproin"
DEFAULT_TEMPLATES = {}

logger = logging.getLogger("curate-bids")


class Template:
    """
    Represents a project-level template for organizing data.

    Args:
        data (dict): The json configuration for the template
        templates (list): The optional existing map of templates by name.

    Attributes:
        namespace (str): The namespace where resolved template data is displayed.
        description (str): The optional description of the template.
        definitions (dict): The map of template definitions.
        rules (list): The list of if rules for applying templates.
        extends (string): The optional name of the template to extend.
        exclude_rules (list): The optional list of rules to exclude from a parent template.
    """

    def __init__(self, data, templates=None):
        if data:
            self.namespace = data.get("namespace")
            self.description = data.get("description", "")
            self.definitions = data.get("definitions", {})
            self.rules = data.get("rules", [])
            self.upload_rules = data.get("upload_rules", [])
            self.resolvers = data.get("resolvers", [])
            self.custom_initializers = data.get("initializers", [])

            self.extends = data.get("extends")
            self.exclude_rules = data.get("exclude_rules", [])
        else:
            raise Exception("data is required")

        if templates:
            self.do_extend(templates)

        resolver = jsonschema.RefResolver.from_schema({"definitions": self.definitions})
        self.resolve_refs(resolver, self.definitions)
        self.compile_resolvers()
        self.compile_rules()
        self.compile_custom_initializers()

    def do_extend(self, templates):
        """
        Implements the extends logic for this template.

        Args:
            templates (list): The existing list of templates.
        """
        if not self.extends:
            return

        if self.extends not in templates:
            raise Exception("Could not find parent template: {0}".format(self.extends))

        parent = templates[self.extends]

        if not self.namespace:
            self.namespace = parent.namespace

        my_rules = self.rules
        my_defs = self.definitions
        my_resolvers = self.resolvers

        # Extend definitions
        self.definitions = parent.definitions.copy()
        for key, value in my_defs.items():
            self.definitions[key] = value

        # Extend rules, after filtering excluded rules
        filtered_rules = filter(lambda x: x.id not in self.exclude_rules, parent.rules)
        self.rules = my_rules + list(filtered_rules)

        # Extend resolvers
        self.resolvers = my_resolvers + parent.resolvers

    def compile_rules(self):
        """
        Converts the rule dictionaries on this object to Rule class objects.
        """
        for i in range(0, len(self.rules)):
            rule = self.rules[i]
            if not isinstance(rule, Rule):
                self.rules[i] = Rule(rule)

        for i in range(0, len(self.upload_rules)):
            upload_rule = self.upload_rules[i]
            if not isinstance(upload_rule, Rule):
                self.upload_rules[i] = Rule(upload_rule)

    def compile_resolvers(self):
        """
        Walk through the definitions
        """
        self.resolver_map = {}
        for i in range(0, len(self.resolvers)):
            res = self.resolvers[i]
            if not isinstance(res, resolver.Resolver):
                res = resolver.Resolver(self.namespace, res)

            # Create a mapping of template id to resolver
            for tmpl in res.templates:
                if tmpl not in self.resolver_map:
                    self.resolver_map[tmpl] = []
                self.resolver_map[tmpl].append(res)

    def compile_custom_initializers(self):
        """
        Map custom initializers by rule id
        """
        self.initializer_map = {}
        for init in self.custom_initializers:
            rule = init.get("rule")
            if not rule:
                continue
            del init["rule"]
            if rule not in self.initializer_map:
                self.initializer_map[rule] = []
            self.initializer_map[rule].append(init)

    def apply_custom_initialization(self, rule_id, info, context):
        """
        Apply custom initialization templates for the given rule

        Args:
            rule_id (str): The id of the matched rule
            info (dict): The info object to update
            context (dict): The current context
        """
        if rule_id in self.initializer_map:
            for init in self.initializer_map[rule_id]:
                if "where" in init:
                    if not test_where_clause(init["where"], context):
                        continue

                apply_initializers(init["initialize"], info, context)

    def validate(self, templateDef, info):
        """
        Validate info against a template definition schema.

        Args:
            templateDef (dict): The template definition (schema)
            info (dict): The info object to validate

        Returns:
            list(string): A list of validation errors if invalid, otherwise an empty list.
        """
        if "_validator" not in templateDef:
            templateDef["_validator"] = jsonschema.Draft4Validator(templateDef)

        return list(sorted(templateDef["_validator"].iter_errors(info), key=str))

    def resolve_refs(self, resolver, obj, parent=None, key=None):
        """
        Resolve all references found in the definitions tree.

        Args:
            resolver (jsonschema.RefResolver): The resolver instance
            obj (object): The object to resolve
            parent (object): The parent object
            key: The key to the parent object
        """
        if isinstance(obj, dict):
            if parent and "$ref" in obj:
                ref, result = resolver.resolve(obj["$ref"])
                parent[key] = result
            else:
                for k in obj.keys():
                    self.resolve_refs(resolver, obj[k], obj, k)
        elif isinstance(obj, list):
            for i in range(len(obj)):
                self.resolve_refs(resolver, obj[i], obj, i)


class Rule:
    """
    Represents a matching rule for applying template definitions to resources or files within a project.

    Args:
        data (dict): The rule definition as a dictionary.

    Attributes:
        id (string): The optional rule id.
        template (str): The name of the template id to apply when this rule matches.
        initialize (dict): The optional set of initialization rules when this rule matches.
        conditions (dict): The set of conditions that must be true for this rule to match.
    """

    def __init__(self, data):
        self.id = data.get("id", "")
        self.template = data.get("template")
        self.initialize = data.get("initialize", {})
        if self.template is None:
            raise Exception('"template" field is required!')
        self.conditions = data.get("where")
        if not self.conditions:
            raise Exception('"where" field is required!')

    def test(self, context):
        """
        Test if the given context matches this rule.

        Args:
            context (dict): The context, which includes the hierarchy and current container

        Returns:
            bool: True if the rule matches the given context.
        """
        return test_where_clause(self.conditions, context)

    def initializeProperties(self, info, context):
        """
        Attempts to resolve initial values of BIDS fields from context.

        Template properties can now include an "initialize" field that gives instructions on how to attempt to
        initialize a field based on context. Within the initialize object, there are a list of keys to extract
        from the context, and currently regular expressions to match against the extracted fields. If the regex
        matches, then the "value" group will be extracted and assigned. Otherwise if 'take' is True for an initialization
        spec, we will copy that value into the field.

        Args:
            context (dict): The full context object
            info (dict): The BIDS data to update, if matched
        """
        apply_initializers(self.initialize, info, context)
        handle_run_counter_initializer(self.initialize, info, context)


def apply_initializers(initializers, info, context):
    """
    Attempts to resolve initial values of BIDS fields from context.

    In theory logging here only occurs on things that successfully match a BIDS template.

    Args:
        initializers (dict): The list of initializer specifications
        context (dict): The full context object
        info (dict): The BIDS data to update, if matched
    """
    for propName, propDef in initializers.items():
        resolvedValue = None

        if isinstance(propDef, dict):
            if "$switch" in propDef:
                resolvedValue = handle_switch_initializer(propDef["$switch"], context)
                if not resolvedValue:
                    logger.debug(f"Unable to match switch case {propDef['$switch']}")

            else:
                for key, valueSpec in propDef.items():
                    # Lookup the value of the key
                    value = utils.dict_lookup(context, key)
                    if value is not None:
                        # Regex matching must provide a 'value' group
                        if "$regex" in valueSpec:
                            regex_list = valueSpec["$regex"]
                            if not isinstance(regex_list, list):
                                regex_list = [regex_list]

                            for regex in regex_list:
                                # when searching, cast value as str, in case it's a list
                                m = re.search(regex, str(value))
                                if m is not None:
                                    resolvedValue = m.group("value")
                                    break
                            if m is None:
                                logger.debug(
                                    f"Unable to match regex <{regex_list}> to <{value}>"
                                )

                        # 'take' will just copy the value
                        elif "$take" in valueSpec and valueSpec["$take"]:
                            resolvedValue = value

                        if "$format" in valueSpec and resolvedValue:
                            resolvedValue = utils.format_value(
                                valueSpec["$format"], resolvedValue
                            )

                        if resolvedValue:
                            break

                    elif key == "$value":
                        resolvedValue = valueSpec

                    else:
                        if key != "$run_counter":  # run counters are handled later
                            logger.debug(
                                f"Metadata key <{key}> does not exist on this object"
                            )
        else:
            resolvedValue = propDef

        # Allows resolved value to be a blank string ""
        if resolvedValue is not None:
            info[propName] = resolvedValue


def handle_switch_initializer(switchDef, context):
    """Evaluate the switch statement on the context to return value"""

    def switch_regex_case(value, regex_pattern):
        result = re.match(regex_pattern, str(value))
        return bool(result)

    value = utils.dict_lookup(context, switchDef["$on"])
    logger.debug(f"value is {value}")
    if isinstance(value, list):
        value = set(value)

    comparators = {"$eq": operator.eq, "$regex": switch_regex_case, "$neq": operator.ne}

    for caseDef in switchDef["$cases"]:
        if "$default" in caseDef:
            return caseDef.get("$value")

        compOperation = None
        for comparator in comparators.keys():
            compValue = caseDef.get(comparator)
            if compValue:
                compOperation = comparators[comparator]
                break
        if isinstance(compValue, list):
            compValue = set(compValue)

        if compOperation:
            its_a_match = compOperation(value, compValue)
            if its_a_match:
                logger.debug(f'match for {compValue} : {caseDef.get("$value")}')
                return caseDef.get("$value")
            else:
                logger.debug(
                    f'no match for {compValue} for value {caseDef.get("$value")}'
                )

    if "$default" in caseDef:
        logger.debug(f'returning default {caseDef.get("$value")}')
        return caseDef.get("$value")

    return None


def handle_run_counter_initializer(initializers, info, context):
    counter = context.get("run_counters")
    if not counter:
        return

    for propName, propDef in initializers.items():
        if isinstance(propDef, dict) and "$run_counter" in propDef:
            current = info.get(propName)
            if current == "+" or current == "=":
                key = propDef["$run_counter"]["key"]
                key = utils.process_string_template(key, context)

                counter = counter[key]
                if current == "+":
                    info[propName] = counter.next()
                else:
                    info[propName] = counter.current()


def test_where_clause(conditions, context):
    """
    Test if the given context matches this rule.

    Args:
        context (dict): The context, which includes the hierarchy and current container

    Returns:
        bool: True if the rule matches the given context.
    """

    for field, match in conditions.items():
        if "$" in field:
            outcome_vals = []
            if isinstance(match, dict):
                outcome_vals.append(
                    determine_nested(field, match, context, nested_match_values=[])
                )
            else:
                # multi-level condition
                for sub_match in match:
                    outcome_vals.append(
                        determine_nested(
                            field, sub_match, context, nested_match_values=[]
                        )
                    )
            return determine_condition_outcome(field, outcome_vals)
        else:
            value = utils.dict_lookup(context, field)
            if not processValueMatch(value, match, context, field):
                return False

    return True


def processValueMatch(value, match, context, condition=None):
    """
    Helper function that recursively performs value matching.
    Args:
        value: The value to match
        match: The matching rule
    Returns:
        bool: The result of matching the value against the match spec.
    """

    if condition in ("$or", "$and"):
        logger.debug("Checking %s", condition)
        # Handle top-level clauses
        match_values = []
        for m in match.items():
            field = m[0]
            deeper_match = m[1]
            # Nested conditions are defined by lists of conditions
            if "$" in field and isinstance(deeper_match, list):
                for deep_element in deeper_match:
                    match_values.append(
                        determine_nested(
                            field, deep_element, context, nested_match_values=[]
                        )
                    )
            else:
                # simple condition
                value = utils.dict_lookup(context, field)
                match_values.append(processValueMatch(value, deeper_match, context))

        return determine_condition_outcome(condition, match_values)

    if isinstance(match, dict):
        # Deeper processing
        if "$in" in match:
            # Check if value is in list
            if isinstance(value, list):
                for item in value:
                    if item in match["$in"]:
                        logger.debug(f"Success: <{item}> matches <{match['$in']}>")
                        return True
                logger.debug(f"Failed: {value} not in {match['$in']}")
                return False
            elif isinstance(value, six.string_types):
                for item in match["$in"]:
                    if item in value:
                        logger.debug(f"Success: <{item}> matches <{match['$in']}>")
                        return True
                logger.debug(f"Failed: <{value}> not in {match['$in']}")
                return False
            return value in match["$in"]

        elif "$not" in match:
            # Negate result of nested match
            return not processValueMatch(value, match["$not"], context)

        elif "$regex" in match:
            regex = re.compile(match["$regex"])

            if isinstance(value, list):
                for item in value:
                    if regex.search(item) is not None:
                        logger.debug(f"Success: <{item}> found in <{match['$regex']}>")
                        return True

                logger.debug(f"Failed: No match for regex {regex}")
                return False

            if value is None:
                logger.debug(f"Failed: No match for regex {regex}")
                return False

            return regex.search(str(value)) is not None

    else:
        if value == match:
            matched = True
        elif isinstance(value, list) and len(value) == 1 and value[0] == match:
            matched = True
        else:
            matched = False

        if matched:
            logger.debug(f"Success: <{value}> matches <{match}>")
        else:
            logger.debug(f"Failed: <{value}> does not match <{match}>")
        return matched


def determine_nested(top_key, deeper_match, context, nested_match_values=[]):
    """
    Match multiple conditions from a given rule.
    Args
        top_key (str): top-level key, which may be a criterion field or logic keyword. If a criterion, then
        deeper_match (dict, list): sub-conditions or condition criteria to be evaluated.
        context: provides file's metadata for the search
        nested_match_values (optional, list): for complex conditions/searches, a running list
                    of boolean results must be passed to return the full list of booleans for
                    ultimate appraisal of the condition.
    Returns
        Boolean for the condition
    """
    if "$" in top_key:
        # Test for (a) logic keyword and (b) nesting
        keys_to_test = [k for k in deeper_match.keys() if "$" in k]
        if keys_to_test and (any(isinstance(i, dict) for i in deeper_match.values())):
            for nested_key, match_vals in deeper_match.items():
                # Nested constraints
                if isinstance(match_vals, dict) and len(match_vals) > 1:
                    for deepest_field, deepest_match in match_vals.items():
                        result = determine_nested(
                            deepest_field,
                            deepest_match,
                            context,
                            nested_match_values=nested_match_values,
                        )
                        nested_match_values.append(result)
                else:
                    nested_match_values.append(
                        determine_simple_condition(nested_key, match_vals, context)
                    )
            # For nested conditions, need to overwrite the match values list with single boolean for the nested condition
            if len(keys_to_test) == 1:
                return determine_condition_outcome(keys_to_test[0], nested_match_values)
            else:
                logger.error("Need to revisit multi-condition logic.")
        else:
            # Multiple constraints
            for nested_key, match_vals in deeper_match.items():
                nested_match_values.append(
                    determine_simple_condition(nested_key, match_vals, context)
                )
            # For nested conditions, need to overwrite the match values list with single boolean for the nested condition
            return determine_condition_outcome(top_key, nested_match_values)

    else:
        # single constraint
        return determine_simple_condition(top_key, deeper_match, context)


def determine_simple_condition(key, match_vals, context):
    """
    Streamlines the process of finding the value stored for a given image so that
    the value can be checked against the list of acceptable values from the condition.
    Args
        key (str): field from the metadata to check
        match_vals (list): acceptable values for the condition, given by the rule
        context: provides metadata for the image
    Returns
        Boolean (or occasionally none, if value is not found)
    """
    value = utils.dict_lookup(context, key)
    logger.debug("Testing if %s is in %s", value, match_vals)
    return processValueMatch(value, match_vals, context)


def determine_condition_outcome(condition, match_values):
    """
    Resolve lists of logical outcomes from any number of conditions.
    Args:
        condition(str): "$or" or "$and"
        match_values (list): list of booleans produced by match processes
    Returns
        Boolean to resolve the condition or error due to unexpected condition keyword
    """
    if "or" in condition:
        return any(match_values)
    elif "and" in condition:
        return all(match_values)
    else:
        logger.error("Expected or/and not %s", condition)


def loadTemplates(templates_dir=None):
    """
    Load all templates in the given (or default) directory

    Args:
        templates_dir (string): The optional directory to load templates from.
    """
    results = {}

    if templates_dir is None:
        script_dir = os.path.dirname(os.path.realpath(__file__))
        templates_dir = os.path.join(script_dir, "../templates")

    # Load all templates from the templates directory
    for fname in os.listdir(templates_dir):
        path = os.path.join(templates_dir, fname)
        name, ext = os.path.splitext(fname)
        if ext == ".json" and os.path.isfile(path):
            results[name] = loadTemplate(path)

    return results


def loadTemplate(path, templates=None):
    """
    Load the template at path

    Args:
        path (str): The path to the template to load
        templates (dict): The mapping of template names to template defintions.
    Returns:
        Template: The template that was loaded (otherwise throws)
    """
    with open(path, "r") as f:
        data = json.load(f)

    data = utils.normalize_strings(data)

    if templates is None:
        templates = DEFAULT_TEMPLATES

    return Template(data, templates)


DEFAULT_TEMPLATES = loadTemplates()
DEFAULT_TEMPLATE = DEFAULT_TEMPLATES.get(DEFAULT_TEMPLATE_NAME)
BIDS_V1_TEMPLATE = DEFAULT_TEMPLATES.get(BIDS_V1_TEMPLATE_NAME)
REPROIN_TEMPLATE = DEFAULT_TEMPLATES.get(REPROIN_TEMPLATE_NAME)

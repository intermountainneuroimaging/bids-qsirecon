from . import utils


class Filter:
    """
    Simple wrapper for a matching filter that can be applied to a context.

    Args:
        fields(dict): The field to value(s) mapping.
    """

    def __init__(self, fields):
        self.fields = fields

    def test(self, context):
        """
        Test context to see if it passes this filter. Top-level clauses (properties) are
        logically ANDed, and lists of values are logically ORed.

        Args:
            context (dict): The context to check

        Returns:
            bool: True if every top level clause matched
        """
        for prop, filter_value in self.fields.items():
            prop_val = utils.dict_lookup(context, prop)
            if isinstance(filter_value, list):
                if prop_val not in filter_value:
                    return False
            else:
                if prop_val != filter_value:
                    return False
        return True


class Resolver:
    """
    Compiled resolver rule

    Args:
        namespace (str): The template namespace
        resolverDef (dict): The resolver properties dictionary

    Attributes:
        namespace: The template namespace
        id: The optional resolver id
        templates: The list of templates this resolver applies to
        update_field: The field to be updated with the resolved result
        filter_field: The field that contains the user-defined filter
        container_type: The type of container this resolver should match
        resolve_for: The level that resolution for this resolver should take place (e.g. session)
        format: The format string for resolved values
        value: The path to the value to copy, if not using a format string
    """

    def __init__(self, namespace, resolverDef):
        self.namespace = namespace
        self.id = resolverDef.get("id")
        self.templates = resolverDef.get("templates", [])
        self.update_field = resolverDef.get("update")
        self.filter_field = resolverDef.get("filter")
        self.container_type = resolverDef.get("type")
        self.resolve_for = resolverDef.get("resolveFor")
        self.format = resolverDef.get("format")
        self.value = resolverDef.get("value")

        if self.format and self.value:
            print(
                'WARNING: Because "format" is specified, "value" will be ignored for resolver: {}'.format(
                    self.id
                )
            )

    def resolve(self, context):
        """
        Resolve update_field for context by matching and formatting children of session.

        Args:
            context (dict): The context to update
        """
        results = []

        parent = context.get(self.resolve_for)
        if not parent:
            return

        # Determine filter fields, and add namespace prefix for matching
        filter_fields = utils.dict_lookup(context, self.filter_field, {})
        base_fields = {}
        if self.container_type:
            base_fields["container_type"] = self.container_type

        filters = []
        for entry in filter_fields:
            fields = base_fields.copy()
            for k, v in entry.items():
                key = "{}.info.{}.{}".format(self.container_type, self.namespace, k)
                fields[key] = v
            filters.append(Filter(fields))

        # Iterate through the contexts in the session, collecting matches
        for ctx in parent.context_iter():
            for filt in filters:
                if filt.test(ctx):
                    if self.format:
                        results.append(utils.process_string_template(self.format, ctx))
                    elif self.value:
                        value = utils.dict_lookup(ctx, self.value, None)
                        if value:
                            if results and results != value:
                                print(
                                    "WARNING: multiple different matches when resolving results, will take last match!"
                                )
                            results = value

        # Finally update the field specified
        utils.dict_set(context, self.update_field, results)

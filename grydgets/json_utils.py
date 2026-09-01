import jq


def extract_json_path(data, json_path):
    """Extract data via a simple path like "field[0].subfield"."""
    json_path_list = list()
    for segment in json_path.replace("]", "").split("."):
        sub_segments = segment.split("[")
        json_path_list.append(sub_segments[0])
        if len(sub_segments) > 1:
            json_path_list += [int(array_index) for array_index in sub_segments[1:]]
    while json_path_list:
        data = data[json_path_list.pop(0)]
    return data


def extract_with_jq(data, jq_expression):
    """Extract data with a jq expression, returning the first result."""
    return jq.compile(jq_expression).input_value(data).first()


def extract_data(data, json_path=None, jq_expression=None):
    """Extract data using json_path and/or jq_expression, json_path applied first.

    Raises ValueError if neither is given.
    """
    if json_path is None and jq_expression is None:
        raise ValueError("Either json_path or jq_expression must be provided")

    if json_path:
        data = extract_json_path(data, json_path)

    if jq_expression:
        data = extract_with_jq(data, jq_expression)

    return data

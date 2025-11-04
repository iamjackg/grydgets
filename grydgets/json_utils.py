import jq


def extract_json_path(data, json_path):
    """Extract data using simple JSON path notation.

    Args:
        data: The JSON data structure
        json_path: Path string like "field[0].subfield"

    Returns:
        Extracted data
    """
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
    """Extract data using jq expression.

    Args:
        data: The JSON data structure
        jq_expression: jq expression string like ".field[0].subfield"

    Returns:
        Extracted data (first result if multiple results)
    """
    return jq.compile(jq_expression).input_value(data).first()


def extract_data(data, json_path=None, jq_expression=None):
    """Extract data using either json_path or jq_expression.

    This function provides a unified interface for data extraction with backwards
    compatibility. If both are provided, json_path is applied first, then jq.

    Args:
        data: The JSON data structure
        json_path: Optional simple JSON path like "field[0].subfield"
        jq_expression: Optional jq expression like ".field[0] | select(.active)"

    Returns:
        Extracted data

    Raises:
        ValueError: If neither json_path nor jq_expression is provided
    """
    if json_path is None and jq_expression is None:
        raise ValueError("Either json_path or jq_expression must be provided")

    # Apply json_path first if provided
    if json_path:
        data = extract_json_path(data, json_path)

    # Apply jq expression if provided
    if jq_expression:
        data = extract_with_jq(data, jq_expression)

    return data

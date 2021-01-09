def extract_json_path(data, json_path):
    json_path_list = list()
    for segment in json_path.replace("]", "").split("."):
        sub_segments = segment.split("[")
        json_path_list.append(sub_segments[0])
        if len(sub_segments) > 1:
            json_path_list += [int(array_index) for array_index in sub_segments[1:]]
    while json_path_list:
        data = data[json_path_list.pop(0)]
    return data

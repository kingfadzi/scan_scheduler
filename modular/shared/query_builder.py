def build_query(payload):
    # Validate that payload is a dict
    if not isinstance(payload, dict):
        raise ValueError("Input must be a dictionary.")

    # Unpack payload if wrapped in 'payload'
    if 'payload' in payload:
        inner_payload = payload['payload']
    else:
        inner_payload = payload

    # Ensure the inner_payload is a non-empty dict
    if not isinstance(inner_payload, dict) or not inner_payload:
        raise ValueError("The provided payload does not contain any filter values.")

    filter_mapping = {
        'repo_id': 'bitbucket_repositories.repo_id',
        'host_name': 'combined_repo_metrics.host_name',
        'activity_status': 'combined_repo_metrics.activity_status',
        'status': 'bitbucket_repositories.status',  # Added repository status field
        'tc': 'combined_repo_metrics.tc',
        'main_language': 'combined_repo_metrics.main_language',
        'classification_label': 'combined_repo_metrics.classification_label',
        'app_id': 'combined_repo_metrics.app_id',
        'number_of_contributors': 'combined_repo_metrics.number_of_contributors'
    }

    select_cols = [
        "bitbucket_repositories.repo_id as repo_id",
        "bitbucket_repositories.status as status",
        "bitbucket_repositories.clone_url_ssh as clone_url_ssh",
        "bitbucket_repositories.updated_on as updated_on"
    ]

    # Add columns from combined_repo_metrics with aliases (except for repo_id)
    for key, col in filter_mapping.items():
        if key not in ['repo_id', 'status']:  # Exclude repo_id and status since they are already included
            select_cols.append(f"{col} as {key}")

    select_clause = "SELECT " + ", ".join(select_cols)
    base_query = f"""
        {select_clause}
        FROM bitbucket_repositories
        JOIN combined_repo_metrics 
          ON combined_repo_metrics.repo_id = bitbucket_repositories.repo_id
        WHERE 1=1
    """

    filters = []

    for key, column in filter_mapping.items():
        if key in inner_payload:
            values = inner_payload[key]
            if not values:
                raise ValueError(f"Filter for '{key}' cannot be empty.")

            if key == 'repo_id':
                filters.append(f"LOWER({column}) LIKE LOWER('%{values[0]}%')")
            else:
                if all(isinstance(v, str) for v in values):
                    formatted_values = ", ".join(f"LOWER('{v.lower()}')" for v in values)
                    filters.append(f"LOWER({column}) IN ({formatted_values})")
                else:
                    formatted_values = ", ".join(str(v) for v in values)
                    filters.append(f"{column} IN ({formatted_values})")

    if not filters:
        raise ValueError("No valid filters provided. Query would select all rows.")

    final_query = base_query + " AND " + " AND ".join(filters)
    return final_query

# Example usage:
if __name__ == "__main__":
    payload_example = {
        "payload": {
            'repo_id': ['abc'],
            'host_name': ['github.com'],
            'activity_status': ['ACTIVE'],
            'status': ['ARCHIVED'],  # Example repository status filter
            'tc': ['some_tc_value'],
            'main_language': ['Python'],
            'classification_label': ['A'],
            'app_id': ['555'],
            'number_of_contributors': [5]
        }
    }

    try:
        query = build_query(payload_example)
        print("Constructed Query:")
        print(query)
    except ValueError as e:
        print("Error:", e)
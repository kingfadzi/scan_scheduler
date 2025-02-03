def build_query(payload):

    filter_mapping = {
        'repo_id': 'bitbucket_repositories.repo_id',
        'host_name': 'combined_repo_metrics.host_name',
        'activity_status': 'combined_repo_metrics.activity_status',
        'tc': 'combined_repo_metrics.tc',
        'main_language': 'combined_repo_metrics.main_language',
        'classification_label': 'combined_repo_metrics.classification_label',
        'app_id': 'combined_repo_metrics.app_id',
        'number_of_contributors': 'combined_repo_metrics.number_of_contributors'
    }

    select_cols = ["bitbucket_repositories.*"]
    for key, col in filter_mapping.items():
        if key != 'repo_id':
            select_cols.append(col)
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
        if key in payload:
            values = payload[key]
            if not values:
                continue
            if key == 'repo_id':
                filters.append(f"LOWER({column}) LIKE LOWER('%{values[0]}%')")
            else:
                if all(isinstance(v, str) for v in values):
                    formatted_values = ", ".join(f"LOWER('{v.lower()}')" for v in values)
                    filters.append(f"LOWER({column}) IN ({formatted_values})")
                else:
                    formatted_values = ", ".join(str(v) for v in values)
                    filters.append(f"{column} IN ({formatted_values})")
    if filters:
        base_query += " AND " + " AND ".join(filters)
    return base_query

if __name__ == "__main__":
    payload_example = {
        'repo_id': ['crAPI'],
        'host_name': ['github.com'],
        'activity_status': ['ACTIVE'],
        #'tc': ['some_tc_value'],
        'main_language': ['Java','HTML'],
        'classification_label': ['Code -> Small'],
        #'app_id': ['555'],
        #'number_of_contributors': [5]
    }
    query = build_query(payload_example)
    print("Constructed Query:", query)

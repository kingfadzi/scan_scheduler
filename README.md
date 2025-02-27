# scheduler

### Python
``prefect deployment run fundamental-metrics-flow/fundamentals --params '{"payload": {"host_name": ["github.com"], "activity_status": ["ACTIVE"], "main_language": ["Python"]}}'``

``prefect deployment run component-patterns-flow/component-patterns --params '{"payload": {"host_name": ["github.com"], "activity_status": ["ACTIVE"], "main_language": ["Python"]}}'``

``prefect deployment run vulnerabilities-flow/vulnerabilities --params '{"payload": {"host_name": ["github.com"], "activity_status": ["ACTIVE"], "main_language": ["Python"]}}'``

``prefect deployment run standards-assessment-flow/standards-assessment --params '{"payload": {"host_name": ["github.com"], "activity_status": ["ACTIVE"], "main_language": ["Python"]}}'``


### All

``prefect deployment run fundamental-metrics-flow/fundamentals --params '{"payload": {"host_name": ["github.com"], "activity_status": ["ACTIVE"]}}'``

``prefect deployment run component-patterns-flow/component-patterns --params '{"payload": {"host_name": ["github.com"], "activity_status": ["ACTIVE"]}}'``

``prefect deployment run vulnerabilities-flow/vulnerabilities --params '{"payload": {"host_name": ["github.com"], "activity_status": ["ACTIVE"]}}'``

``prefect deployment run standards-assessment-flow/standards-assessment --params '{"payload": {"host_name": ["github.com"], "activity_status": ["ACTIVE"]}}'``

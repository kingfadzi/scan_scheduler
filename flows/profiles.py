import asyncio

from config.config import Config
from flows.profiles.main_flow import main_batch_profile_flow

if __name__ == "__main__":
    asyncio.run(main_batch_profile_flow(
        payload={
            "payload": {
                "host_name": [Config.GITLAB_HOSTNAME, Config.BITBUCKET_HOSTNAME],
                "activity_status": ['ACTIVE'],
                "main_language": ["c#", "go", "java", "JavaScript", "Ruby", "Python"]
            }
        }
    ))

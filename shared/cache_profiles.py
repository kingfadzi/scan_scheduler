import json
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from shared.repo_profile_cache import RepoProfileCache
from shared.aggregator import build_profile
from shared.models import Repository

# Replace this with your actual DB URL
DATABASE_URL = "postgresql://postgres:postgres@192.168.1.188:5432/gitlab-usage"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def main():
    session = SessionLocal()

    repos = session.query(Repository.repo_id).all()

    for repo_id, in repos:
        profile = build_profile(session, repo_id)

        if profile:
            existing = session.query(RepoProfileCache).filter_by(repo_id=repo_id).first()

            if existing:
                existing.profile_json = json.dumps(profile)
            else:
                new_cache = RepoProfileCache(
                    repo_id=repo_id,
                    profile_json=json.dumps(profile)
                )
                session.add(new_cache)

            print(f"Profile cached for {repo_id}")

    session.commit()
    session.close()
    print("All profiles cached.")

if __name__ == "__main__":
    main()
from sqlalchemy import Column, String, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class RepoProfileCache(Base):
    __tablename__ = "repo_profile_cache"

    repo_id = Column(String, primary_key=True)
    profile_json = Column(Text, nullable=False)
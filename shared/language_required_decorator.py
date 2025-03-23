import functools
import logging
from typing import Dict, Any
from pprint import pformat
from shared.utils import Utils

def language_required(*languages):
    """Decorator to enforce repository language requirements."""

    expected_lower = {str(lang).lower() for lang in languages}
    original_list = languages

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, repo_dir: str, repo: Dict[str, Any], *args, **kwargs):
            logger = getattr(self, 'logger', logging.getLogger('default'))

            try:
                # Validate repo structure
                if not isinstance(repo, dict):
                    raise TypeError(f"Expected dict for repo, got {type(repo)}")
                if 'repo_id' not in repo:
                    raise KeyError("repo missing 'repo_id'")

                repo_id = repo["repo_id"]

                logger.debug("Repo metadata:\n%s", pformat({
                    'id': repo_id,
                    'keys': list(repo.keys()),
                    'type': type(repo).__name__
                }))

                # Get language information
                main_language = Utils().get_repo_main_language(repo_id)
                logger.debug("Language raw response: %s (%s)", main_language, type(main_language))

                if not main_language:
                    logger.warning("No language detected for repo %s", repo_id)
                    return f"skipped: No language detected for {repo_id}"

                # Safe language normalization
                try:
                    received_lang = str(main_language).strip().lower()
                except Exception as e:
                    logger.error("Language normalization failed: %s", str(e), exc_info=True)
                    return f"error: Invalid language format for {repo_id}"

                logger.debug("Language comparison:\n- Expected: %s\n- Received: %s",
                             original_list, received_lang)

                if received_lang not in expected_lower:
                    logger.warning("Language mismatch for %s. Skipping", repo_id)
                    return f"skipped: {repo_id} requires {original_list} (found {main_language})"

                return func(self, repo_dir, repo, *args, **kwargs)

            except Exception as e:
                repo_context = {
                    'id': repo.get('repo_id', 'unknown') if isinstance(repo, dict) else 'invalid-repo',
                    'type': type(repo).__name__,
                    'content': pformat(vars(repo)) if hasattr(repo, '__dict__') else pformat(repo)
                }
                logger.error("Language check failed:\n%s", pformat(repo_context), exc_info=True)
                return f"error: Language validation failed - {str(e)}"

        return wrapper
    return decorator

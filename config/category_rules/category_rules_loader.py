import os
import re
import yaml
import logging
from config.config import Config

class RuleLoader:

    _RULES_PATH = Config.CATEGORY_RULES_PATH
    _RULES_MAPPING = {
        "python": "python",
        "java-archive": "java",
        "npm": "javascript",
        "gem": "ruby",
        "dotnet": "dotnet",
        "go-module": "go"
    }

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self._compiled_rules_cache = {}

    def load_rules(self, package_type: str):
        package_type = package_type.lower()
        component = self._RULES_MAPPING.get(package_type)
        if not component:
            self.logger.warning(f"No rule mapping for package type: {package_type}")
            return []

        full_path = os.path.join(self._RULES_PATH, component)
        compiled_list = []

        self.logger.info(f"[{package_type}] Loading rules from: {full_path}")

        if os.path.isdir(full_path):
            files = [os.path.join(full_path, f) for f in os.listdir(full_path) if f.endswith((".yml", ".yaml"))]
            self.logger.debug(f"[{package_type}] Found {len(files)} rule files in directory")
        else:
            files = [full_path]
            self.logger.debug(f"[{package_type}] Using single rule file")

        for file_path in files:
            try:
                self.logger.debug(f"[{package_type}] Processing file: {os.path.basename(file_path)}")
                with open(file_path, 'r') as f:
                    rules = yaml.safe_load(f)

                for cat in rules.get('categories', []):
                    category_name = cat['name']
                    subcats = cat.get('subcategories', [])

                    for sub in subcats:
                        sub_name = sub.get('name', 'unnamed')
                        frameworks = sub.get('frameworks', [])

                        if frameworks:
                            for framework in frameworks:
                                fw_name = framework.get('name', 'unnamed')
                                patterns = framework.get('patterns', [])
                                for pattern in patterns:
                                    compiled_list.append((
                                        re.compile(pattern, flags=re.IGNORECASE),
                                        category_name,
                                        sub_name,
                                        fw_name
                                    ))
                        else:
                            patterns = sub.get('patterns', [])
                            for pattern in patterns:
                                compiled_list.append((
                                    re.compile(pattern, flags=re.IGNORECASE),
                                    category_name,
                                    sub_name,
                                    ""
                                ))

                self.logger.info(f"[{package_type}] Loaded {len(rules.get('categories', []))} categories from {os.path.basename(file_path)}")

            except Exception as e:
                self.logger.error(f"[{package_type}] Failed to load rules: {str(e)}", exc_info=True)

        self.logger.info(f"[{package_type}] Total compiled rules: {len(compiled_list)}")
        return compiled_list

    def get_supported_languages(self):
        return list(self._RULES_MAPPING.keys())


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("RuleLoaderMain")

    rule_loader = RuleLoader(logger=logger)

    # Optional: language as command-line argument
    if len(sys.argv) > 1:
        language = sys.argv[1].lower()
        compiled_rules = rule_loader.load_rules(language)
        print(f"Loaded {len(compiled_rules)} compiled rules for package type '{language}':")
        to_show = min(10, len(compiled_rules))
        for i, rule in enumerate(compiled_rules[:to_show]):
            print(f"Rule {i+1}: Pattern={rule[0].pattern}, Category={rule[1]}, Subcategory={rule[2]}, Framework={rule[3]}")
        if len(compiled_rules) > 10:
            print(f"...and {len(compiled_rules) - 10} more not printed for brevity.")
        if not compiled_rules:
            print(f"No rules found for language: {language}")
    else:
        print("No language specified. Printing all rules for all supported languages:\n")
        for lang in rule_loader.get_supported_languages():
            compiled_rules = rule_loader.load_rules(lang)
            print(f"\n--- {lang} ({len(compiled_rules)} rules) ---")
            to_show = min(10, len(compiled_rules))
            for i, rule in enumerate(compiled_rules[:to_show]):
                print(f"Rule {i+1}: Pattern={rule[0].pattern}, Category={rule[1]}, Subcategory={rule[2]}, Framework={rule[3]}")
            if len(compiled_rules) > 10:
                print(f"...and {len(compiled_rules) - 10} more not printed for brevity.")
            if not compiled_rules:
                print(f"No rules found for language: {lang}")

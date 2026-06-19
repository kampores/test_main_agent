# AGENTS.md

## Coding Rules

- Do not hardcode configuration values, file paths, model names, API URLs, credentials, business constants, or label texts in the code files. Separate code and data by loading them from environment variables or configuration files (e.g., YAML).
- Apply object-oriented design when adding or modifying non-trivial behaviors. Use classes with highly cohesive responsibilities and avoid writing giant procedural functions.
- You do not need to create custom logging classes from the very beginning. However, once the project's codebase exceeds 2000 lines of code, create dedicated classes for `logging`, `config`, and `error` handling inside the `common` directory and centralize their usage. Do not use `print()` for runtime logging.

## Korean Commenting Rules

- All files containing Korean characters must be saved with UTF-8 encoding.
- Code comments and docstrings must be written in Korean.
- Write a Korean docstring explaining the purpose and intent for all functions and classes.
- Write Korean comments for class variables explaining the domain meaning, allowed ranges, and subsequent data flow. Avoid comments that merely repeat the variable name or its type.

## Python File Header Rules

- At the beginning of each `.py` file, record the creation date, designer name, affiliation, and email addresses in comments.
- Place headers before the module docstring, imports, and executable code.
- Follow this header format:

```python
# 작성일: YYYY-MM-DD
# 설계자: 이름
# 설계자 소속: 회사명
# 설계자 이메일: name@example_corp.com, name@example_personnel.com
```

## README and Documentation Rules

- Avoid trivial, tautological explanations in README documents or CLI options (e.g., "A is A").
  - *Bad example: `--dialect: The dialect to be used.`*
  - *Good example: `--dialect: The database syntax format (e.g., duckdb, postgres) where the queries will be executed.`*
- Write detailed Korean documentation including explanations of terms, concrete mechanisms, and examples so that users can clearly understand the tools' roles, input domain meanings, and scope of configurations.

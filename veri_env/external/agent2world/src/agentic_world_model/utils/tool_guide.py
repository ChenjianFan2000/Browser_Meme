

SANDBOX_USING_GUIDE = """
Basic patterns
--------------

1) Run a simple Python snippet
   run_code("print('ok')")

2) Run a standalone script with Bash
   run_bash("python path/to/script.py")

Running tests with pytest
-------------------------

Recommended flow:

1. Save your test file(s) into the sandbox:
   file_tool('save', file_path="tests/test_env.py", content=\"\"\"<pytest code here>\"\"\")

2. Run pytest with explicit file path and disable capture
   (to avoid sandbox restrictions on /dev/null):
   run_bash("pytest -q --tb=short --capture=no tests/test_env.py",
            env_requirements=["pytest==8.2.0"])

   Notes:
   - Always specify the file path, not just the directory.
   - Use `--capture=no` (or `-s`) to prevent pytest from opening /dev/null.
   - `-q` makes output quieter, `--tb=short` gives concise tracebacks.

"""
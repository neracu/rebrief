Create an integration test script `scripts/test_drive.py` to test the `rebrief` utility on real projects.

Requirements:
1. The script must automate the execution of `rebrief scan` for a specified list of paths to local repositories.
2. Implement a function that takes a project path as an argument, runs the parsers, generates a report, and prints a brief quality metric to the console:
   - How many risks were found.
   - How many commits were filtered out.
   - Whether the report file was successfully created.
3. The script must contain an `if __name__ == ‘__main__’:` block that accepts command-line arguments via `sys.argv` (paths to the test folders) so that it can be run as follows: `python scripts/test_drive.py /path/to/old/project1 /path/to/ai/project2`.
4. Use `colorama` to display the output in a visually appealing way (Green for SUCCESS / Red for FAIL) so you can visually monitor the utility’s stress test on messy code.

The code should be utilitarian, simple, and kept separate from the main package.
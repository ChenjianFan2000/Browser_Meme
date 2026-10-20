# Warning: All of the following code must be included in each verification, and no part may be omitted.
import re
from tarski.io import PDDLReader
from tarski.syntax.formulas import *
import traceback

def extract_pddl(text):
    if not isinstance(text, str):
        raise TypeError("Input 'text' must be a string")
    if not text.strip():
        raise ValueError("Input 'text' cannot be empty")
        
    pattern = r"```pddl\\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches == []:
        pattern = r"```\\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
    
    if not matches:
        raise ValueError("No PDDL code block found in the text")
        
    pddl = max(matches, key=len).replace('```pddl', '').replace('```', '').strip()
    if not pddl:
        raise ValueError("Extracted PDDL code is empty")
        
    return pddl

def validate_pddl_domain(pddl_domain, raise_on_error=True):
    try:
        reader = PDDLReader(raise_on_error=raise_on_error)
        reader.parse_domain_string(pddl_domain)
        return True, 'Success'
    except Exception as e:
        exception_type = type(e).__name__
        traceback_info = traceback.format_exc()
        error_message = f"{exception_type}: {e}"
        return False, error_message

def parse_actions(pddl_domain):
    reader = PDDLReader(raise_on_error=True)
    reader.parse_domain_string(pddl_domain)
    return reader.problem.actions

def parse_predicates(pddl_domain):
    reader = PDDLReader(raise_on_error=True)
    reader.parse_domain_string(pddl_domain)
    predicate_map = {}
    for pred in reader.problem.language.predicates:
        if str(pred.symbol) not in ['=', '!=']:
            predicate_map[str(pred.symbol)] = pred.arity
    return predicate_map

import argparse
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(
        description="Validate a PDDL domain from a single file and print actions/predicates if valid."
    )
    parser.add_argument("file", help="Path to a file containing RAW PDDL domain code.")
    args = parser.parse_args()

    # Read PDDL domain from file
    try:
        with open(args.file, 'r', encoding='utf-8') as f:
            pddl_domain = f.read().strip()
    except FileNotFoundError:
        print(f"Error: File {args.file} not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file {args.file}: {e}")
        sys.exit(1)

    # Validate syntax
    is_valid, message = validate_pddl_domain(pddl_domain)
    print(f"PDDL Validation: {is_valid}")
    if not is_valid:
        print(f"Error: {message}")
    else:
        print("PDDL domain is syntactically correct!")
        
        # Parse and display domain components
        try:
            actions = parse_actions(pddl_domain)
            predicates = parse_predicates(pddl_domain)
            print(f"Actions found: {list(actions.keys())}")
            print(f"Predicates found: {list(predicates.keys())}")
        except Exception as e:
            print(f"Error parsing domain components: {e}")

if __name__ == "__main__":
    main()
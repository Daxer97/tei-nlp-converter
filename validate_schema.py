#!/usr/bin/env python3
"""
Validate a custom schema before deployment

Usage:
    python3 validate_schema.py schemas/medical.json
    python3 validate_schema.py schemas/*.json
"""
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple


def validate_schema_file(schema_path: Path) -> bool:
    """Validate a schema JSON file"""
    print(f"\n{'=' * 60}")
    print(f"Validating: {schema_path.name}")
    print('=' * 60)

    try:
        # 1. Load JSON
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        print(f"✅ Valid JSON format")

        # 2. Check required fields
        required = ["domain", "title", "annotation_strategy"]
        missing = [f for f in required if f not in schema]
        if missing:
            print(f"❌ Missing required fields: {', '.join(missing)}")
            return False
        print(f"✅ All required fields present")
        print(f"   Domain: {schema['domain']}")
        print(f"   Title: {schema['title']}")

        # 3. Validate annotation_strategy
        valid_strategies = ["inline", "standoff", "mixed"]
        if schema["annotation_strategy"] not in valid_strategies:
            print(f"❌ Invalid annotation_strategy: {schema['annotation_strategy']}")
            print(f"   Must be one of: {', '.join(valid_strategies)}")
            return False
        print(f"✅ Valid annotation_strategy: {schema['annotation_strategy']}")

        # 4. Validate entity_mappings
        if "entity_mappings" in schema:
            if not isinstance(schema["entity_mappings"], dict):
                print(f"❌ entity_mappings must be a dictionary")
                return False

            mappings = schema["entity_mappings"]
            print(f"✅ Valid entity_mappings ({len(mappings)} entity types)")

            # Check for DEFAULT
            if "DEFAULT" not in mappings:
                print(f"⚠️  Warning: No DEFAULT mapping defined")
                print(f"   It's recommended to include: \"DEFAULT\": \"name\"")
            else:
                print(f"   DEFAULT → {mappings['DEFAULT']}")

            # List some mappings
            sample_count = min(5, len(mappings))
            sample_items = list(mappings.items())[:sample_count]
            print(f"   Sample mappings:")
            for entity_type, tei_element in sample_items:
                print(f"      {entity_type} → {tei_element}")
            if len(mappings) > sample_count:
                print(f"      ... and {len(mappings) - sample_count} more")

        else:
            print(f"⚠️  No entity_mappings defined (will use provider defaults)")

        # 5. Check for common optional fields
        optional_checks = {
            "description": "Description",
            "include_pos": "POS tagging",
            "include_lemma": "Lemmatization",
            "include_dependencies": "Dependencies",
            "include_analysis": "Analysis section",
            "use_paragraphs": "Paragraph structure",
            "additional_tags": "Additional TEI tags",
            "classification": "Text classification",
            "text_class": "Classification category"
        }

        present = []
        missing_optional = []
        for field, description in optional_checks.items():
            if field in schema:
                present.append((field, schema[field]))
            else:
                missing_optional.append(description)

        if present:
            print(f"\n✅ Optional fields present:")
            for field, value in present:
                if isinstance(value, bool):
                    print(f"   {field}: {value}")
                elif isinstance(value, list):
                    print(f"   {field}: {len(value)} items")
                else:
                    print(f"   {field}: {value}")

        if missing_optional:
            print(f"\nℹ️  Optional fields not set (using defaults):")
            for desc in missing_optional[:5]:  # Show first 5
                print(f"   - {desc}")
            if len(missing_optional) > 5:
                print(f"   ... and {len(missing_optional) - 5} more")

        # 6. Final validation
        print(f"\n{'=' * 60}")
        print(f"✅ Schema '{schema['domain']}' is VALID and ready to use!")
        print('=' * 60)
        return True

    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON syntax: {e}")
        print(f"   Line {e.lineno}, Column {e.colno}")
        return False
    except FileNotFoundError:
        print(f"❌ File not found: {schema_path}")
        return False
    except Exception as e:
        print(f"❌ Validation error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python3 validate_schema.py <schema.json> [<schema2.json> ...]")
        print("\nExamples:")
        print("  python3 validate_schema.py schemas/medical.json")
        print("  python3 validate_schema.py schemas/*.json")
        sys.exit(1)

    schema_files = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        if path.is_file():
            schema_files.append(path)
        else:
            print(f"⚠️  Skipping non-file: {arg}")

    if not schema_files:
        print("❌ No valid schema files provided")
        sys.exit(1)

    print(f"\n📋 Validating {len(schema_files)} schema file(s)...")

    results = []
    for schema_file in schema_files:
        result = validate_schema_file(schema_file)
        results.append((schema_file.name, result))

    # Summary
    print(f"\n{'=' * 60}")
    print("VALIDATION SUMMARY")
    print('=' * 60)

    passed = sum(1 for _, result in results if result)
    failed = len(results) - passed

    for filename, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {filename}")

    print(f"\nTotal: {len(results)} | Passed: {passed} | Failed: {failed}")

    if failed > 0:
        print(f"\n❌ {failed} schema(s) failed validation")
        sys.exit(1)
    else:
        print(f"\n✅ All schemas are valid!")
        sys.exit(0)


if __name__ == "__main__":
    main()

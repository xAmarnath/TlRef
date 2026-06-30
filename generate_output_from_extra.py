import json

# Load extra.json
with open('extra.json', 'r') as f:
    extra = json.load(f)

# Create output.json structure from extra.json
output = {
    "constructors": [],
    "methods": [],
    "metadata": {
        "total_constructors": len(extra['constructors']),
        "total_methods": len(extra['methods']),
        "successful": len(extra['constructors']) + len(extra['methods']),
        "failed": 0
    }
}

# Convert extra.json constructors to output.json format
for ctor in extra['constructors']:
    item = {
        "name": ctor["name"],
        "category": "constructor",
        "description": ctor.get("description", ""),
        "fields": ctor.get("fields", []),
        "result_type": "",
        "can_be_used_by": ctor.get("can_be_used_by", []),
        "business_connection": False,
        "errors": [],
        "related_pages": [],
        "raw_tl": ""
    }
    output["constructors"].append(item)

# Convert extra.json methods to output.json format
for method in extra['methods']:
    item = {
        "name": method["name"],
        "category": "method",
        "description": method.get("description", ""),
        "fields": method.get("params", []),  # params in extra become fields in output
        "result_type": method.get("returns", ""),
        "can_be_used_by": method.get("can_be_used_by", []),
        "business_connection": False,
        "errors": [],
        "related_pages": [],
        "raw_tl": ""
    }
    output["methods"].append(item)

# Save as output.json
with open('output.json', 'w') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"✓ Generated output.json from extra.json")
print(f"  - Constructors: {len(output['constructors'])}")
print(f"  - Methods: {len(output['methods'])}")
print(f"  - Total items: {output['metadata']['successful']}")

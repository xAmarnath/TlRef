"""
TL Schema Documentation Scraper

This script parses a schema.tl file, extracts types (constructors) and methods,
fetches their documentation from corefork.telegram.org, and saves to JSON.
"""

import re
import json
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from typing import Optional
import time
import sys


@dataclass
class FieldInfo:
    name: str
    type: str
    description: str = ""


@dataclass
class ErrorInfo:
    code: str
    type: str
    description: str


@dataclass
class TLEntry:
    name: str
    category: str  # "constructor" or "method"
    description: str = ""
    fields: list[FieldInfo] = field(default_factory=list)
    result_type: str = ""
    can_be_used_by: list[str] = field(default_factory=list)  # ["users", "bots"]
    business_connection: bool = False
    errors: list[ErrorInfo] = field(default_factory=list)
    related_pages: list[str] = field(default_factory=list)
    raw_tl: str = ""


def get_text_with_spaces(element) -> str:
    """
    Extract text from an HTML element, preserving spaces between elements.
    This handles cases where links and other tags are stripped without adding spaces.
    """
    if element is None:
        return ""
    
    # Get text with separator to preserve spacing
    text = element.get_text(separator=' ', strip=True)
    
    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def parse_schema_file(filepath: str) -> tuple[list[str], list[str]]:
    """
    Parse schema.tl file and extract constructor names and method names.
    Returns (constructors, methods)
    """
    constructors = []
    methods = []
    
    is_functions_section = False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('//'):
                continue
            
            # Check for section markers
            if line == '---functions---':
                is_functions_section = True
                continue
            elif line == '---types---':
                is_functions_section = False
                continue
            
            # Parse TL definition line
            # Format: name#id params = Type;
            # Or: namespace.name#id params = Type;
            match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)#[0-9a-fA-F]+', line)
            if match:
                name = match.group(1)
                if is_functions_section:
                    methods.append(name)
                else:
                    constructors.append(name)
    
    return constructors, methods


def parse_tl_definition(tl_line: str) -> tuple[str, list[FieldInfo], str]:
    """
    Parse a TL schema definition line and extract fields.
    Returns (name, fields, result_type)
    
    Example: inputMediaPhoto#b3ba0635 flags:# spoiler:flags.1?true id:InputPhoto ttl_seconds:flags.0?int = InputMedia;
    Returns: ("inputMediaPhoto", [FieldInfo(...), ...], "InputMedia")
    """
    # Match the TL definition pattern: name#hash params = Type;
    match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_\.]*)\#[0-9a-fA-F]+\s*(.*?)\s*=\s*([a-zA-Z_][a-zA-Z0-9_\.]*)', tl_line)
    if not match:
        return None, [], None
    
    name = match.group(1)
    params_str = match.group(2).strip()
    result_type = match.group(3)
    
    fields = []
    
    if params_str:
        # Split parameters by space, but handle {t:Type} patterns in vectors
        # Use regex to match param patterns
        # Pattern: param_name:type or param_name:flags.N?type
        param_pattern = r'([a-zA-Z_][a-zA-Z0-9_]*):([^\s]+)'
        
        for param_match in re.finditer(param_pattern, params_str):
            field_name = param_match.group(1)
            field_type = param_match.group(2)
            
            # Skip the flags field itself (type is #)
            if field_type == '#':
                continue
            
            fields.append(FieldInfo(
                name=field_name,
                type=field_type,
                description=""
            ))
    
    return name, fields, result_type


def load_schema_definitions(filepath: str) -> dict:
    """
    Load all TL definitions from schema.tl file.
    Returns a dict mapping name -> (fields, result_type, raw_tl)
    """
    definitions = {}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            
            # Skip empty lines, comments, and section markers
            if not line or line.startswith('//') or line.startswith('---'):
                continue
            
            # Parse the line
            name, fields, result_type = parse_tl_definition(line)
            if name:
                definitions[name] = {
                    'fields': fields,
                    'result_type': result_type,
                    'raw_tl': line
                }
    
    return definitions


def fetch_documentation(name: str, category: str, schema_definitions: dict = None) -> Optional[TLEntry]:
    """
    Fetch documentation for a type/method from corefork.telegram.org
    category: "constructor" or "method"
    schema_definitions: Optional dict with fallback data from schema.tl
    """
    base_url = f"https://corefork.telegram.org/{category}/{name}"
    
    try:
        response = requests.get(base_url, timeout=30)
        if response.status_code != 200:
            print(f"[{response.status_code}] Failed to fetch: {base_url}")
            # Use schema fallback if available
            if schema_definitions and name in schema_definitions:
                return create_entry_from_schema(name, category, schema_definitions[name])
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        entry = TLEntry(name=name, category=category)
        
        # Get main description (usually the first <p> after <h1> or in dev_page_content)
        dev_content = soup.find('div', id='dev_page_content')
        if dev_content:
            # The description is usually the first paragraph
            first_p = dev_content.find('p')
            if first_p:
                entry.description = get_text_with_spaces(first_p)
        
        # Get raw TL definition from code block
        code_block = soup.find('code')
        if code_block:
            # Find the specific line for this entry
            code_text = code_block.get_text()
            for line in code_text.split('\n'):
                if name in line and '#' in line:
                    entry.raw_tl = line.strip()
                    break
        
        # Parse Parameters table
        tables = soup.find_all('table')
        for table in tables:
            # Check if this is the parameters table
            prev_h3 = table.find_previous('h3')
            if prev_h3:
                header_text = prev_h3.get_text(strip=True).lower()
                
                if 'parameter' in header_text:
                    rows = table.find_all('tr')
                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) >= 3:
                            field_name = cols[0].get_text(strip=True)
                            field_type = cols[1].get_text(strip=True)
                            field_desc = get_text_with_spaces(cols[2]) if len(cols) > 2 else ""
                            
                            if field_name:  # Skip empty rows
                                entry.fields.append(FieldInfo(
                                    name=field_name,
                                    type=field_type,
                                    description=field_desc
                                ))
                
                elif 'error' in header_text:
                    rows = table.find_all('tr')
                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) >= 3:
                            error_code = cols[0].get_text(strip=True)
                            error_type = cols[1].get_text(strip=True)
                            error_desc = get_text_with_spaces(cols[2]) if len(cols) > 2 else ""
                            
                            if error_code and error_type:
                                entry.errors.append(ErrorInfo(
                                    code=error_code,
                                    type=error_type,
                                    description=error_desc
                                ))
        
        # Get Result/Type
        h3_tags = soup.find_all('h3')
        for h3 in h3_tags:
            h3_text = h3.get_text(strip=True).lower()
            if h3_text in ['result', 'type']:
                # Get the next sibling that's a link or text
                next_elem = h3.find_next_sibling()
                if next_elem:
                    link = next_elem.find('a') if hasattr(next_elem, 'find') else None
                    if link:
                        entry.result_type = link.get_text(strip=True)
                    else:
                        entry.result_type = next_elem.get_text(strip=True)
        
        # Check who can use this method (bots/users)
        page_text = soup.get_text()
        
        if 'Both users and bots can use this method' in page_text:
            entry.can_be_used_by = ['users', 'bots']
        elif 'Only users can use this method' in page_text:
            entry.can_be_used_by = ['users']
        elif 'Only bots can use this method' in page_text:
            entry.can_be_used_by = ['bots']
        elif 'Bots can use this method' in page_text:
            entry.can_be_used_by.append('bots')
        
        # Check for business connection
        if 'business connection' in page_text.lower():
            entry.business_connection = True
        
        # Get related pages
        for h3 in h3_tags:
            if 'related page' in h3.get_text(strip=True).lower():
                # Find all h4 siblings until next h3
                sibling = h3.find_next_sibling()
                while sibling and sibling.name != 'h3':
                    if sibling.name == 'h4':
                        link = sibling.find('a')
                        if link:
                            entry.related_pages.append(link.get_text(strip=True))
                    sibling = sibling.find_next_sibling()
        
        # If we got no useful data from the webpage, use schema fallback
        if not entry.description and not entry.fields and schema_definitions and name in schema_definitions:
            schema_entry = create_entry_from_schema(name, category, schema_definitions[name])
            # Merge schema data into entry
            entry.fields = schema_entry.fields
            entry.result_type = schema_entry.result_type
            entry.raw_tl = schema_entry.raw_tl
        
        return entry
        
    except requests.RequestException as e:
        print(f"[ERROR] Request failed for {base_url}: {e}")
        # Use schema fallback if available
        if schema_definitions and name in schema_definitions:
            return create_entry_from_schema(name, category, schema_definitions[name])
        return None
    except Exception as e:
        print(f"[ERROR] Parsing failed for {name}: {e}")
        # Use schema fallback if available
        if schema_definitions and name in schema_definitions:
            return create_entry_from_schema(name, category, schema_definitions[name])
        return None


def create_entry_from_schema(name: str, category: str, schema_data: dict) -> TLEntry:
    """
    Create a TLEntry from schema.tl data.
    """
    return TLEntry(
        name=name,
        category=category,
        description="",
        fields=schema_data['fields'],
        result_type=schema_data['result_type'],
        raw_tl=schema_data['raw_tl']
    )


def entry_to_dict(entry: TLEntry) -> dict:
    """Convert TLEntry to a JSON-serializable dict"""
    return {
        "name": entry.name,
        "category": entry.category,
        "description": entry.description,
        "fields": [{"name": f.name, "type": f.type, "description": f.description} for f in entry.fields],
        "result_type": entry.result_type,
        "can_be_used_by": entry.can_be_used_by,
        "business_connection": entry.business_connection,
        "errors": [{"code": e.code, "type": e.type, "description": e.description} for e in entry.errors],
        "related_pages": entry.related_pages,
        "raw_tl": entry.raw_tl
    }


def scrape_all(schema_path: str, output_path: str, max_workers: int = 10):
    """
    Main function to scrape all documentation.
    """
    print(f"Parsing schema file: {schema_path}")
    constructors, methods = parse_schema_file(schema_path)
    
    print(f"Found {len(constructors)} constructors and {len(methods)} methods")
    
    # Load schema definitions for fallback
    print(f"Loading schema definitions for fallback...")
    schema_definitions = load_schema_definitions(schema_path)
    print(f"Loaded {len(schema_definitions)} schema definitions")
    
    # Prepare all tasks
    tasks = []
    for name in constructors:
        tasks.append((name, "constructor"))
    for name in methods:
        tasks.append((name, "method"))
    
    print(f"Total items to fetch: {len(tasks)}")
    
    results = {
        "constructors": [],
        "methods": [],
        "metadata": {
            "total_constructors": len(constructors),
            "total_methods": len(methods),
            "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "https://corefork.telegram.org",
            "fallback_source": "schema.tl"
        }
    }
    
    # Use ThreadPoolExecutor for concurrent fetching
    completed = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks with schema definitions for fallback
        future_to_task = {
            executor.submit(fetch_documentation, name, category, schema_definitions): (name, category)
            for name, category in tasks
        }
        
        # Process results as they complete
        for future in as_completed(future_to_task):
            name, category = future_to_task[future]
            completed += 1
            
            try:
                entry = future.result()
                if entry:
                    if category == "constructor":
                        results["constructors"].append(entry_to_dict(entry))
                    else:
                        results["methods"].append(entry_to_dict(entry))
                    print(f"[{completed}/{len(tasks)}] ✓ {category}/{name}")
                else:
                    failed += 1
                    print(f"[{completed}/{len(tasks)}] ✗ {category}/{name} (no data)")
            except Exception as e:
                failed += 1
                print(f"[{completed}/{len(tasks)}] ✗ {category}/{name} - Error: {e}")
    
    # Update metadata
    results["metadata"]["successful"] = len(results["constructors"]) + len(results["methods"])
    results["metadata"]["failed"] = failed
    
    # Save to JSON
    print(f"\nSaving results to: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\nDone!")
    print(f"  Constructors scraped: {len(results['constructors'])}")
    print(f"  Methods scraped: {len(results['methods'])}")
    print(f"  Failed: {failed}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Scrape TL schema documentation from corefork.telegram.org')
    parser.add_argument('schema', help='Path to schema.tl file')
    parser.add_argument('-o', '--output', default='tl_documentation.json', help='Output JSON file path')
    parser.add_argument('-w', '--workers', type=int, default=10, help='Number of concurrent workers (default: 10)')
    
    args = parser.parse_args()
    
    scrape_all(args.schema, args.output, args.workers)


if __name__ == '__main__':
    main()

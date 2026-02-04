"""
TL Documentation HTML Generator

Builds static HTML pages from the scraped JSON documentation.
- index.html with search functionality
- Individual pages for each constructor and method
"""

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from html import escape

# Current TL Schema version
TL_VERSION = 224



@lru_cache(maxsize=4096)
def clean_description(text: str) -> str:
    """
    Clean description text by:
    - Removing special characters like »
    - Handling format specifiers like %d
    - Fixing any remaining spacing issues
    """
    if not text:
        return text
    
    # Remove » « and similar chars
    text = re.sub(r'[»«›‹]', '', text)
    
    # Replace %d, %s, %f etc. with readable placeholders
    text = re.sub(r'%d', '<number>', text)
    text = re.sub(r'%s', '<value>', text)
    text = re.sub(r'%f', '<decimal>', text)
    text = re.sub(r'%\d*[dsfx]', '<value>', text)
    
    # Fix concatenated words (from old data without proper spacing)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    #text = re.sub(r'([a-zA-Z])(the|a|an|to|in|on|of|for|is|are|this|that|with|from|by|at|or|and)\b', r'\1 \2', text, flags=re.IGNORECASE)
    
    # Fix number-letter concatenation
    text = re.sub(r'(\d)([A-Za-z])', r'\1 \2', text)
    text = re.sub(r'([A-Za-z])(\d)', r'\1 \2', text)
    
    # Fix missing spaces after punctuation
    text = re.sub(r'\.([A-Za-z])', r'. \1', text)
    text = re.sub(r',([A-Za-z])', r', \1', text)
    text = re.sub(r':([A-Za-z])', r': \1', text)
    
    # Clean up punctuation spacing
    text = re.sub(r'\.\.+', '.', text)
    text = re.sub(r'\s+([.,;:])', r'\1', text)
    
    # Normalize multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def load_documentation(json_path: str) -> dict:
    """Load the JSON documentation file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


@lru_cache(maxsize=4096)
def get_output_path(name: str, category: str) -> str:
    """
    Get the output path for a constructor/method.
    e.g., messages.sendMessage -> methods/messages/sendMessage.html
    """
    if '.' in name:
        namespace, item_name = name.rsplit('.', 1)
        return f"{category}s/{namespace}/{item_name}.html"
    else:
        return f"{category}s/{name}.html"


def linkify_type(type_str: str, root_path: str = ".", type_map: dict = None) -> str:
    """
    Convert type references to links.
    e.g., Vector<InputMessage> -> Vector&lt;<a href="...">InputMessage</a>&gt;
    
    type_map: dict mapping type names to their constructors (if provided, will link to type pages)
    """
    import re
    
    # Common primitive types that shouldn't be linked
    primitives = {'int', 'long', 'double', 'string', 'bytes', 'true', 'Bool', '#', 'Object'}
    
    def make_link(type_name: str) -> str:
        # Strip flags prefix like "flags.0?"
        clean_name = re.sub(r'^flags\.\d+\?', '', type_name)
        
        if clean_name in primitives or clean_name.startswith('flags'):
            return escape(type_name)
        
        # Check if it's a Vector type
        vector_match = re.match(r'Vector<(.+)>', clean_name)
        if vector_match:
            inner = vector_match.group(1)
            inner_link = make_link(inner)
            return f'Vector&lt;{inner_link}&gt;'
        
        # Check if this is a known interface/generic type with multiple constructors
        if type_map and clean_name in type_map:
            href = f"{root_path}/types/{clean_name}.html"
        elif '.' in clean_name:
            # Namespaced constructor
            namespace, name = clean_name.rsplit('.', 1)
            href = f"{root_path}/constructors/{namespace}/{name}.html"
        else:
            # Could be a constructor or type - check type_map
            if type_map and clean_name in type_map:
                href = f"{root_path}/types/{clean_name}.html"
            else:
                href = f"{root_path}/constructors/{clean_name}.html"
        
        # Preserve the original string (with flags prefix) in display
        if type_name != clean_name:
            prefix = type_name[:type_name.index(clean_name)]
            return f'{escape(prefix)}<a href="{href}">{escape(clean_name)}</a>'
        
        return f'<a href="{href}">{escape(clean_name)}</a>'
    
    return make_link(type_str)


@lru_cache(maxsize=4096)
def to_go_name(name: str) -> str:
    """
    Convert TL name to Go method name.
    e.g., messages.sendMessage -> MessagesSendMessage
    e.g., inputMediaEmpty -> InputMediaEmpty
    """
    # Split by dots and underscores
    parts = name.replace('.', '_').split('_')
    result = []
    for part in parts:
        # Handle camelCase within each part
        # Split on lowercase to uppercase transitions
        words = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+', part)
        if words:
            result.extend(word.capitalize() for word in words)
        else:
            result.append(part.capitalize())
    return ''.join(result)


# Common interface types and their example implementations
INTERFACE_EXAMPLES = {
    'InputMedia': 'InputMediaPhoto',
    'InputPeer': 'InputPeerUser',
    'InputUser': 'InputUserSelf',
    'InputChannel': 'InputChannel',
    'InputDocument': 'InputDocument',
    'InputPhoto': 'InputPhoto',
    'InputFile': 'InputFile',
    'InputGeoPoint': 'InputGeoPoint',
    'InputChatPhoto': 'InputChatUploadedPhoto',
    'InputNotifyPeer': 'InputNotifyPeer',
    'InputPrivacyKey': 'InputPrivacyKeyStatusTimestamp',
    'InputPrivacyRule': 'InputPrivacyValueAllowAll',
    'ReplyMarkup': 'ReplyKeyboardMarkup',
    'InputBotInlineMessage': 'InputBotInlineMessageText',
    'InputBotInlineResult': 'InputBotInlineResult',
    'InputStickeredMedia': 'InputStickeredMediaPhoto',
    'InputWebFileLocation': 'InputWebFileLocation',
    'InputSecureFile': 'InputSecureFileUploaded',
    'InputEncryptedFile': 'InputEncryptedFileUploaded',
    'MessageEntity': 'MessageEntityBold',
    'KeyboardButton': 'KeyboardButton',
    'Update': 'UpdateNewMessage',
    'Chat': 'Chat',
    'User': 'User',
    'Message': 'Message',
    'InputReplyTo': 'InputReplyToMessage',
    'InputQuickReplyShortcut': 'InputQuickReplyShortcut',
    'SuggestedPost': 'SuggestedPost',
}


def get_type_example(field_type: str, include_comment: bool = False, expand_struct: bool = False) -> str:
    """
    Get an example value for a given TL type.
    Returns a Go code snippet representing the type.
    
    expand_struct: if True, show struct fields for complex types
    """
    import re
    
    # Strip flags prefix like "flags.0?"
    clean_type = re.sub(r'^flags\.\d+\?', '', field_type)
    is_optional = 'flags.' in field_type and '?' in field_type
    
    # Primitives - use realistic example values
    if 'string' in clean_type:
        return '"Hello, World!"'
    elif clean_type in ('int', 'int32'):
        return '42'
    elif clean_type in ('long', 'int64'):
        return 'int64(1234567890)'
    elif clean_type == 'double':
        return '3.14159'
    elif clean_type == 'bytes':
        return '[]byte{0x01, 0x02, 0x03}'
    elif clean_type in ('Bool', 'true'):
        return 'true'
    
    # Vector types
    vector_match = re.match(r'Vector<(.+)>', clean_type)
    if vector_match:
        inner_type = vector_match.group(1)
        inner_go_name = to_go_name(inner_type)
        if inner_type in ('int', 'long', 'string', 'bytes', 'int32', 'int64'):
            return f'[]{inner_type}{{}}'
        # Check if it's an interface type
        if inner_type in INTERFACE_EXAMPLES:
            impl = INTERFACE_EXAMPLES[inner_type]
            impl_go = to_go_name(impl)
            if expand_struct:
                expanded = get_expanded_struct(impl)
                if expanded:
                    return f'[]tg.{inner_go_name}{{{expanded}}}'
            return f'[]tg.{inner_go_name}{{&tg.{impl_go}{{}}}}'
        return f'[]tg.{inner_go_name}{{&tg.{inner_go_name}{{}}}}'
    
    # Complex types - check if it's an interface type
    if clean_type and clean_type[0].isupper():
        go_type_name = to_go_name(clean_type)
        
        # Check if this is a known interface type
        if clean_type in INTERFACE_EXAMPLES:
            impl = INTERFACE_EXAMPLES[clean_type]
            impl_go = to_go_name(impl)
            
            # Expand common structs with their fields
            if expand_struct:
                expanded = get_expanded_struct(impl)
                if expanded:
                    return expanded
            
            if include_comment:
                return f'&tg.{impl_go}{{}}  // or other {clean_type} implementations'
            return f'&tg.{impl_go}{{}}'
        
        # Not an interface type, but still try to expand if requested
        if expand_struct:
            expanded = get_expanded_struct(clean_type)
            if expanded:
                return expanded
        
        return f'&tg.{go_type_name}{{}}'
    
    return 'nil'


# Common struct field expansions for better examples
STRUCT_EXPANSIONS = {
    'InputPeerUser': 'UserID: int64(777000)',  # Telegram service account ID
    'InputPeerChat': 'ChatID: int64(1234567890)',
    'InputPeerChannel': 'ChannelID: int64(1234567890), AccessHash: int64(5678901234567890)',
    'InputUserSelf': '',
    'InputUser': 'UserID: int64(777000), AccessHash: int64(5678901234567890)',
    'InputChannel': 'ChannelID: int64(1234567890), AccessHash: int64(5678901234567890)',
    'InputPhoto': 'ID: int64(5678901234567890), AccessHash: int64(1234567890123456), FileReference: []byte{0x01, 0x02}',
    'InputDocument': 'ID: int64(5678901234567890), AccessHash: int64(1234567890123456), FileReference: []byte{0x01, 0x02}',
    'InputMediaPhoto': 'ID: &tg.InputPhoto{ID: int64(5678901234567890), AccessHash: int64(1234567890123456), FileReference: []byte{0x01}}',
    'InputMediaDocument': 'ID: &tg.InputDocument{ID: int64(5678901234567890), AccessHash: int64(1234567890123456), FileReference: []byte{0x01}}',
    'InputMediaUploadedPhoto': 'File: &tg.InputFile{ID: int64(7654321098765), Parts: 3, Name: "photo.jpg"}',
    'InputMediaUploadedDocument': 'File: &tg.InputFile{ID: int64(7654321098765), Parts: 5, Name: "document.pdf"}, MimeType: "application/pdf", Attributes: []tg.DocumentAttribute{&tg.DocumentAttributeFilename{FileName: "document.pdf"}}',
    'InputFile': 'ID: int64(7654321098765), Parts: 3, Name: "upload.dat"',
    'InputGeoPoint': 'Lat: 40.7128, Long: -74.0060',  # New York coordinates
    'InputReplyToMessage': 'ReplyToMsgID: 42',
    'MessageEntityBold': 'Offset: 0, Length: 11',
    'ReplyKeyboardMarkup': 'Rows: []tg.KeyboardButtonRow{{Buttons: []tg.KeyboardButton{&tg.KeyboardButton{Text: "Click Me"}}}}',
}



def get_expanded_struct(type_name: str) -> str:
    """Get an expanded struct example with fields filled in."""
    go_name = to_go_name(type_name)
    if type_name in STRUCT_EXPANSIONS:
        fields = STRUCT_EXPANSIONS[type_name]
        if fields:
            return f'&tg.{go_name}{{{fields}}}'
        return f'&tg.{go_name}{{}}'
    return None



def generate_gogram_example(item: dict, category: str, type_map: dict = None, go_types_set: set = None) -> str:
    """
    Generate Gogram usage example for a method or constructor.
    
    In Gogram:
    - Methods with ≤5 required params use ONLY positional arguments
    - Methods with >5 required params use ONLY a Params struct
    - Constructors are always created as struct literals
    - If a constructor name matches a type name, add Obj suffix
    """
    name = item['name']
    go_name = to_go_name(name)
    fields = item.get('fields', [])
    
    # Check if constructor name conflicts with a type name
    # If so, Gogram uses the Obj suffix to differentiate
    if category == 'constructor':
        # Check against go_types_set if available, otherwise fall back to type_map
        if go_types_set and go_name in go_types_set:
            go_name = go_name + 'Obj'
        elif type_map and not go_types_set:
            # Fallback logic (less accurate)
            base_name = name.split('.')[-1] if '.' in name else name
            if base_name in type_map:
                go_name = go_name + 'Obj'
    
    if category == 'method':
        # Collect required and optional parameters
        required_params = []
        optional_params = []
        
        for field in fields:
            field_name = field['name']
            field_type = field['type']
            
            # Skip the flags field itself
            if field_name == 'flags' or field_type == '#':
                continue
            
            # Convert to Go param name
            go_param = to_go_name(field_name)
            
            # Check if optional
            is_optional = 'flags.' in field_type and '?' in field_type
            
            # Get example value - expand structs for positional args
            example_val = get_type_example(field_type, include_comment=False, expand_struct=True)
            
            if is_optional:
                optional_params.append((go_param, example_val, field_type))
            else:
                required_params.append((go_param, example_val, field_type))
        
        # Determine result type for the return value comment
        result_type = item.get('result_type', 'Response')
        go_result = to_go_name(result_type) if result_type else 'Response'
        
        # Use positional args ONLY if ≤5 required params AND no optional params
        # If there are optional params, user needs the struct form to set them
        use_positional = len(required_params) <= 5 and len(optional_params) == 0
        
        if use_positional:
            # Use ONLY positional arguments
            args = ', '.join(p[1] for p in required_params)
            
            example = f'''// {go_name} - positional arguments
result, err := client.{go_name}({args})
if err != nil {{
    // handle error
}}
// result is *tg.{go_result}'''
        else:
            # Use Params struct
            params_lines = []
            for p in required_params[:8]:
                params_lines.append(f'    {p[0]}: {p[1]},')
            
            if len(required_params) > 8:
                params_lines.append('    // ...')
            
            if optional_params:
                params_lines.append('')
                params_lines.append('    // Optional fields:')
                for opt in optional_params[:4]:
                    params_lines.append(f'    // {opt[0]}: {opt[1]},')
                if len(optional_params) > 4:
                    params_lines.append('    // ...')
            
            params_str = '\n'.join(params_lines)
            
            example = f'''// {go_name} - using Params struct
result, err := client.{go_name}(&tg.{go_name}Params{{
{params_str}
}})
if err != nil {{
    // handle error
}}
// result is *tg.{go_result}'''
        
    else:  # constructor
        # Generate constructor instantiation example
        required_params = []
        optional_params = []
        
        for field in fields:
            field_name = field['name']
            field_type = field['type']
            
            if field_name == 'flags' or field_type == '#':
                continue
            
            go_param = to_go_name(field_name)
            is_optional = 'flags.' in field_type and '?' in field_type
            example_val = get_type_example(field_type, include_comment=False, expand_struct=True)
            
            if is_optional:
                optional_params.append((go_param, example_val))
            else:
                required_params.append((go_param, example_val))
        
        params_lines = []
        for p in required_params[:6]:
            params_lines.append(f'    {p[0]}: {p[1]},')
        
        if len(required_params) > 6:
            params_lines.append('    // ... more required fields')
        
        if optional_params:
            params_lines.append('')
            params_lines.append('    // Optional fields:')
            for opt in optional_params[:4]:
                params_lines.append(f'    // {opt[0]}: {opt[1]},')
            if len(optional_params) > 4:
                params_lines.append('    // ... more optional fields')
        
        if params_lines:
            params_str = '\n'.join(params_lines)
            example = f'''// Creating {go_name} constructor
obj := &tg.{go_name}{{
{params_str}
}}'''
        else:
            example = f'''// Creating {go_name} constructor
obj := &tg.{go_name}{{}}'''
    
    return example


def highlight_go_code(code: str) -> str:
    """Apply syntax highlighting to Go code."""
    import re
    
    # Escape HTML first
    code = escape(code)
    
    # Keywords
    keywords = r'\b(func|return|if|else|for|range|var|const|type|struct|interface|package|import|defer|go|select|case|default|break|continue|nil|true|false)\b'
    code = re.sub(keywords, r'<span class="keyword">\1</span>', code)
    
    # Comments (// ...)
    code = re.sub(r'(//[^\n]*)', r'<span class="comment">\1</span>', code)
    
    # Strings ("...")
    code = re.sub(r'(&quot;[^&]*?&quot;)', r'<span class="string">\1</span>', code)
    
    # Numbers
    code = re.sub(r'\b(\d+\.?\d*)\b', r'<span class="number">\1</span>', code)
    
    # Type names (tg.SomeType, &tg.SomeType)
    code = re.sub(r'(tg\.)([A-Z][A-Za-z0-9]*)', r'<span class="package">\1</span><span class="type">\2</span>', code)
    
    # Function/method calls (client.Method)
    code = re.sub(r'(client\.)([A-Z][A-Za-z0-9]*)', r'<span class="package">\1</span><span class="function">\2</span>', code)
    
    return code


def get_relative_root(path: str) -> str:
    """Calculate relative path back to root from a given path."""
    depth = path.count('/') 
    if depth == 0:
        return "."
    return "/".join([".."] * depth)





def generate_header(title: str, root_path: str, search_data: list = None, description: str = None, item_type: str = None) -> str:
    """Generate the common header HTML with Instant View support."""
    search_html = ""
    if search_data is not None:
        search_html = f"""
        <div class="search-container">
            <div class="search-wrapper">
                <input type="text" id="search-input" placeholder="Search methods, constructors, types..." autocomplete="off">
                <div id="search-dropdown" class="search-results-dropdown hidden"></div>
            </div>
        </div>
"""
    
    # Meta description for SEO and Instant View
    meta_desc = description if description else f"TL Schema documentation for {title}"
    meta_desc = meta_desc[:160]  # Truncate for meta tag
    
    # Open Graph and Telegram Instant View meta tags
    og_type = "article" if item_type in ('method', 'constructor', 'type') else "website"
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(title)} - Gogram TL Reference</title>
    <meta name="description" content="{escape(meta_desc)}">
    
    <!-- Open Graph / Telegram Instant View -->
    <meta property="og:title" content="{escape(title)} - Gogram TL Reference">
    <meta property="og:description" content="{escape(meta_desc)}">
    <meta property="og:type" content="{og_type}">
    <meta property="og:site_name" content="Gogram TL Reference">
    
    <!-- Telegram Instant View hints -->
    <meta property="article:author" content="AmarnathCJD">
    <meta name="author" content="AmarnathCJD">
    <meta name="telegram:channel" content="@gaborern">
    <meta property="tg:site_verification" content="g7j8/rPFXfhyrq5q0QQV7EsYWv4=">
    
    <link rel="stylesheet" href="{root_path}/css/common.css">
    <script src="{root_path}/js/utils.js"></script>
    <script>
        (function() {{
            const saved = localStorage.getItem('theme');
            const isDark = saved === 'dark';
            if (isDark) document.documentElement.setAttribute('data-theme', 'dark');
        }})();
    </script>
</head>
<body>
    <header>
        <div class="container">
            <a href="{root_path}/index.html" class="logo">Gogram <span>TLRef</span></a>
            <div class="header-right">
                <nav>
                    <a href="{root_path}/index.html">Home</a>
                    <a href="{root_path}/types.html">Types</a>
                    <a href="{root_path}/constructors.html">Constructors</a>
                    <a href="{root_path}/methods.html">Methods</a>
                </nav>
                <button class="theme-toggle" onclick="toggleTheme()" aria-label="Toggle theme">
                    <svg class="sun-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                    </svg>
                    <svg class="moon-icon" style="display:none" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                    </svg>
                </button>
            </div>
        </div>{search_html}
    </header>
""" + (f"""
    <script>
        const rootPath = "{root_path}";
    </script>
    <script src="{root_path}/js/search_index.js"></script>
    <script src="{root_path}/js/search.js"></script>
""" if search_data else "")



def generate_footer() -> str:
    """Generate the common footer HTML."""
    return """
    <footer style="margin-top: 48px; border-top: 1px solid var(--border); padding: 24px 0;">
        <div class="container" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;">
            <div style="color: var(--text-secondary); font-size: 13px;">
                &copy; 2025 Gogram TLRef. Licensed under MIT.
            </div>
            <div style="display: flex; gap: 24px; font-size: 13px;">
                <a href="https://github.com/AmarnathCJD/gogram" target="_blank" style="color: var(--text-secondary);">Gogram</a>
                <a href="https://corefork.telegram.org" target="_blank" style="color: var(--text-secondary);">Telegram Core</a>
                <a href="https://github.com/AmarnathCJD/tl-ref" target="_blank" style="color: var(--text-secondary);">About</a>
            </div>
        </div>
    </footer>
</body>
</html>
"""


def generate_index_page(data: dict) -> str:
    """Generate the main index.html page."""
    constructors = data.get('constructors', [])
    methods = data.get('methods', [])
    metadata = data.get('metadata', {})
    
    # Build search data for index page
    search_data = []
    for item in constructors:
        go_name = to_go_name(item['name'])
        search_data.append({
            "name": item['name'],
            "goDisplay": go_name,
            "searchName": go_name.lower() + " " + item['name'].lower().replace('.', ' '),
            "desc": item.get('description', ''),
            "type": "constructor",
            "path": get_output_path(item['name'], 'constructor')
        })
    for item in methods:
        go_name = to_go_name(item['name'])
        search_data.append({
            "name": item['name'],
            "goDisplay": go_name,
            "searchName": go_name.lower() + " " + item['name'].lower().replace('.', ' '),
            "desc": item.get('description', ''),
            "type": "method",
            "path": get_output_path(item['name'], 'method')
        })
    
    # Get recent items (first 10 of each)
    recent_constructors = constructors[:10]
    recent_methods = methods[:10]
    
    html = generate_header("Home", ".", search_data)
    html += f"""
    <main class="container">
        <div class="hero-section" style="text-align: center; margin-bottom: 32px; padding: 24px 0;">
            <h1 style="font-size: 2.5rem; font-weight: 600; margin-bottom: 12px;">Gogram TL Reference</h1>
            <p style="color: var(--text-secondary); font-size: 1.1rem; max-width: 700px; margin: 0 auto 16px; line-height: 1.6;">
                Complete documentation for Telegram's Type Language (TL) Schema, optimized for <a href="https://github.com/AmarnathCJD/gogram" target="_blank" style="color: var(--accent);">Gogram</a> development.
            </p>
            <div style="display: inline-flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: center;">
                <div style="display: inline-flex; align-items: center; gap: 8px; background: var(--bg-secondary); padding: 6px 14px; border-radius: 20px; border: 1px solid var(--border);">
                    <span style="color: var(--text-secondary); font-size: 12px;">Layer</span>
                    <span style="background: var(--accent); color: white; padding: 2px 8px; border-radius: 10px; font-weight: 600; font-size: 12px;">{TL_VERSION}</span>
                </div>
                <div style="display: inline-flex; align-items: center; gap: 6px; background: var(--bg-secondary); padding: 6px 14px; border-radius: 20px; border: 1px solid var(--border);">
                    <span style="color: var(--constructor); font-weight: 600; font-size: 12px;">{len(constructors)}</span>
                    <span style="color: var(--text-secondary); font-size: 12px;">Constructors</span>
                </div>
                <div style="display: inline-flex; align-items: center; gap: 6px; background: var(--bg-secondary); padding: 6px 14px; border-radius: 20px; border: 1px solid var(--border);">
                    <span style="color: var(--method); font-weight: 600; font-size: 12px;">{len(methods)}</span>
                    <span style="color: var(--text-secondary); font-size: 12px;">Methods</span>
                </div>
            </div>
        </div>
        
        <div class="about-section" style="background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius); padding: 24px; margin-bottom: 32px; text-align: left;">
            <h2 style="font-size: 1rem; font-weight: 600; margin-bottom: 12px;">About TL Types</h2>
            <p style="color: var(--text-secondary); line-height: 1.7; margin-bottom: 12px; text-align: left;">
                The <strong>Type Language (TL)</strong> is a schema language used by Telegram to define its API. It describes constructors (data types) and methods (API calls) that form the MTProto protocol.
            </p>
            <p style="color: var(--text-secondary); line-height: 1.7; margin-bottom: 12px; text-align: left;">
                In <strong>Gogram</strong>, each TL constructor is represented as a Go struct in the <code style="background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px;">telegram</code> package. For example, <code style="background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px;">inputMediaPhoto</code> becomes <code style="background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px;">telegram.InputMediaPhoto</code>.
            </p>
            <p style="color: var(--text-secondary); line-height: 1.7; text-align: left;">
                <strong>Types</strong> are abstract interfaces that can be implemented by multiple constructors. For instance, <code style="background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px;">InputMedia</code> is implemented by <code style="background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px;">InputMediaPhoto</code>, <code style="background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px;">InputMediaDocument</code>, and others.
            </p>
        </div>
        
        <div class="section">
            <h2>Recent Constructors</h2>
            <div class="item-list">
"""
    
    for item in recent_constructors:
        path = get_output_path(item['name'], 'constructor')
        desc = clean_description(item.get('description', '')[:100]) or 'No description'
        go_name = to_go_name(item['name'])
        html += f"""
                <a href="{path}" class="item" data-name="{escape(go_name.lower())} {escape(item['name'].lower())}" data-type="constructor">
                    <span class="item-name">{escape(go_name)}</span>
                    <span class="item-desc">{escape(desc)}</span>
                </a>
"""
    
    html += """
            </div>
            <p><a href="constructors.html" class="view-all">View all constructors →</a></p>
        </div>
        
        <div class="section">
            <h2>Recent Methods</h2>
            <div class="item-list">
"""
    
    for item in recent_methods:
        path = get_output_path(item['name'], 'method')
        desc = clean_description(item.get('description', '')[:100]) or 'No description'
        go_name = to_go_name(item['name'])
        html += f"""
                <a href="{path}" class="item" data-name="{escape(go_name.lower())} {escape(item['name'].lower())}" data-type="method">
                    <span class="item-name">{escape(go_name)}</span>
                    <span class="item-desc">{escape(desc)}</span>
                </a>
"""
    
    html += """
            </div>
            <p><a href="methods.html" class="view-all">View all methods →</a></p>
        </div>
    </main>
"""
    
    html += generate_footer()
    return html


def generate_list_page(items: list, category: str, title: str, search_data: list) -> str:
    """Generate a listing page for all constructors or methods."""
    html = generate_header(title, ".", search_data)
    html += f"""
    <main class="container">
        <div class="page-header">
            <h1>{title}</h1>
            <p class="description">{len(items)} entries</p>
        </div>
        
        <div style="margin-bottom: 20px;">
            <input type="text" id="filter-input" placeholder="Filter {title.lower()}..." autocomplete="off">
        </div>
        
        <div class="item-list" id="items-list">
"""
    
    for item in items:
        path = get_output_path(item['name'], category)
        desc = clean_description(item.get('description', '')[:100]) or 'No description'
        go_name = to_go_name(item['name'])
        html += f"""
            <a href="{path}" class="item" data-name="{escape(go_name.lower())} {escape(item['name'].lower())}">
                <span class="item-name">{escape(go_name)}</span>
                <span class="item-desc">{escape(desc)}</span>
            </a>
"""
    
    html += """
        </div>
    </main>
    
    <script src="js/filter.js"></script>
"""

    
    html += generate_footer()
    return html


def generate_type_page(type_name: str, constructors: list, search_data: list, type_map: dict) -> str:
    """Generate a page for a generic/interface type showing all its constructors."""
    root_path = ".."
    
    type_desc = f"Abstract type representing one of {len(constructors)} possible constructors."
    html = generate_header(type_name, root_path, search_data, type_desc, 'type')
    
    breadcrumb = f'<a href="{root_path}/index.html">Home</a> <span>›</span> <a href="{root_path}/types.html">Types</a> <span>›</span> {type_name}'
    
    go_type_name = to_go_name(type_name)
    
    html += f"""
    <main class="container">
        <article>
        <div class="breadcrumb">{breadcrumb}</div>
        
        <div style="display: flex; justify-content: flex-end; margin-bottom: 8px;">
            <span style="font-size: 11px; color: var(--text-secondary); background: var(--bg-tertiary); padding: 4px 10px; border-radius: 12px;">Layer {TL_VERSION}</span>
        </div>
        
        <header class="page-header">
            <h1>{escape(go_type_name)}</h1>
            <p class="description">{type_desc}</p>
        </header>
        
        <div class="badges">
            <span class="badge badge-type">Type</span>
        </div>
        
        <div class="section">
            <h2>Available Constructors</h2>
            <p style="margin-bottom: 16px; color: var(--text-secondary);">
                In Gogram, this type is represented as <code style="background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px;">tg.{go_type_name}</code> interface.
                Use any of the following constructors:
            </p>
            <div class="item-list">
"""
    
    for item in constructors:
        path = get_output_path(item['name'], 'constructor')
        desc = clean_description(item.get('description', '')[:100]) or 'No description'
        go_name = to_go_name(item['name'])
        html += f"""
            <a href="{root_path}/{path}" class="item" data-name="{escape(go_name.lower())} {escape(item['name'].lower())}">
                <span class="item-name">{escape(go_name)}</span>
                <span class="item-desc">{escape(desc)}</span>
            </a>
"""
    
    html += """
            </div>
        </div>
        
        <div class="example-section">
            <h2>Gogram Example</h2>
            <pre class="example-code">"""
    
    # Generate example showing how to use the interface
    example = f"""// {type_name} is an interface type
// You can use any of the following constructors:
"""
    for item in constructors[:5]:  # Show first 5 as examples
        go_name = to_go_name(item['name'])
        example += f"var _ tg.{go_type_name} = &tg.{go_name}{{}}\n"
    
    if len(constructors) > 5:
        example += f"// ... and {len(constructors) - 5} more constructors\n"
    
    html += highlight_go_code(example)
    html += """</pre>
        </div>
        </article>
    </main>
"""
    
    html += generate_footer()
    return html


def generate_types_list_page(type_map: dict, search_data: list) -> str:
    """Generate a listing page for all generic/interface types."""
    html = generate_header("Types", ".", search_data)
    html += f"""
    <main class="container">
        <div class="page-header">
            <h1>Types</h1>
            <p class="description">{len(type_map)} abstract types</p>
        </div>
        
        <div style="margin-bottom: 20px;">
            <input type="text" id="filter-input" placeholder="Filter types..." autocomplete="off">
        </div>
        
        <div class="item-list" id="items-list">
"""
    
    for type_name, constructors in sorted(type_map.items()):
        desc = f"{len(constructors)} constructor{'s' if len(constructors) != 1 else ''}"
        go_type = to_go_name(type_name)
        html += f"""
            <a href="types/{type_name}.html" class="item" data-name="{escape(go_type.lower())} {escape(type_name.lower())}">
                <span class="item-name">{escape(go_type)}</span>
                <span class="item-desc">{desc}</span>
            </a>
"""
    
    html += """
        </div>
    </main>
    
    <script src="js/filter.js"></script>
"""

    
    html += generate_footer()
    return html



def generate_detail_page(item: dict, category: str, search_data: list, type_map: dict = None, go_types_set: set = None) -> str:
    """Generate a detail page for a constructor or method."""
    path = get_output_path(item['name'], category)
    root_path = get_relative_root(path)
    
    # Clean the description
    description = clean_description(item.get('description', 'No description available'))
    
    go_name = to_go_name(item['name'])
    
    # Add Obj suffix for constructors where name matches a type name
    display_name = go_name
    if category == 'constructor':
        if go_types_set and go_name in go_types_set:
            display_name = go_name + 'Obj'
        elif type_map and not go_types_set and type_map:
            base_name = item['name'].split('.')[-1] if '.' in item['name'] else item['name']
            if base_name in type_map:
                display_name = go_name + 'Obj'
    
    html = generate_header(item['name'], root_path, search_data, description, category)
    
    # Breadcrumb
    if '.' in item['name']:
        namespace, name = item['name'].rsplit('.', 1)
        go_namespace = to_go_name(namespace)
        go_item_name = to_go_name(name)
        # Add Obj suffix in breadcrumb if needed
        if category == 'constructor':
            if go_types_set and go_item_name in go_types_set:
                go_item_name = go_item_name + 'Obj'
            elif type_map and not go_types_set and name in type_map:
                go_item_name = go_item_name + 'Obj'
        breadcrumb = f'<a href="{root_path}/index.html">Home</a> <span>›</span> <a href="{root_path}/{category}s.html">{category.title()}s</a> <span>›</span> {go_namespace} <span>›</span> {go_item_name}'
    else:
        breadcrumb = f'<a href="{root_path}/index.html">Home</a> <span>›</span> <a href="{root_path}/{category}s.html">{category.title()}s</a> <span>›</span> {display_name}'
    
    html += f"""
    <main class="container">
        <article>
        <div class="breadcrumb">{breadcrumb}</div>
        
        <div style="display: flex; justify-content: flex-end; margin-bottom: 8px;">
            <span style="font-size: 11px; color: var(--text-secondary); background: var(--bg-tertiary); padding: 4px 10px; border-radius: 12px;">Layer {TL_VERSION}</span>
        </div>
        
        <header class="page-header">
            <h1>{escape(display_name)}</h1>
            <p class="description">{escape(description)}</p>
        </header>
        
        <div class="badges">
            <span class="badge badge-{category}">{category}</span>
"""
    
    # Usage badges
    can_use = item.get('can_be_used_by', [])
    if 'users' in can_use:
        html += '            <span class="badge badge-user">Users</span>\n'
    if 'bots' in can_use:
        html += '            <span class="badge badge-bot">Bots</span>\n'
    if item.get('business_connection'):
        html += '            <span class="badge badge-business">Business</span>\n'
    
    html += '        </div>'
    
    # Raw TL definition
    if item.get('raw_tl'):
        html += f"""
        <div class="code-block">{escape(item['raw_tl'])}</div>
"""
    
    # Parameters/Fields - skip flags entries
    fields = item.get('fields', [])
    # Filter out flags-related fields
    display_fields = [f for f in fields if f['name'] != 'flags' and f['type'] != '#']
    if display_fields:
        html += """
        <div class="section">
            <h2>Parameters</h2>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Type</th>
                            <th>Description</th>
                        </tr>
                    </thead>
                    <tbody>
"""
        for field in display_fields:
            field_desc = clean_description(field.get('description', ''))
            go_field_name = to_go_name(field['name'])
            html += f"""
                        <tr>
                            <td class="field-name">{escape(go_field_name)}</td>
                            <td class="field-type">{linkify_type(field['type'], root_path, type_map)}</td>
                            <td>{escape(field_desc)}</td>
                        </tr>
"""
        html += """
                    </tbody>
                </table>
            </div>
        </div>
"""
    
    # Result type
    if item.get('result_type'):
        html += f"""
        <div class="result-section">
            <h3>Returns</h3>
            <span class="result-type">{linkify_type(item['result_type'], root_path, type_map)}</span>
        </div>
"""
    
    # Gogram usage example - moved BEFORE errors section
    example = generate_gogram_example(item, category, type_map, go_types_set)
    highlighted_example = highlight_go_code(example)
    html += f"""
        <div class="example-section">
            <h2>Gogram Example</h2>
            <pre class="example-code">{highlighted_example}</pre>
        </div>
"""
    
    # Errors - now AFTER examples
    errors = item.get('errors', [])
    if errors:
        html += """
        <div class="section">
            <h2>Possible Errors</h2>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Code</th>
                            <th>Type</th>
                            <th>Description</th>
                        </tr>
                    </thead>
                    <tbody>
"""
        for error in errors:
            error_desc = clean_description(error.get('description', ''))
            html += f"""
                        <tr>
                            <td class="error-code">{escape(error['code'])}</td>
                            <td class="error-type">{escape(error['type'])}</td>
                            <td>{escape(error_desc)}</td>
                        </tr>
"""
        html += """
                    </tbody>
                </table>
            </div>
        </div>
"""
    
    # Related pages
    related = [r for r in item.get('related_pages', []) if r.strip()]
    if related:
        html += """
        <div class="section">
            <h2>Related Pages</h2>
            <ul class="related-list">
"""
        for page in related:
            html += f'                <li>{escape(page)}</li>\n'
        html += """
            </ul>
        </div>
"""
    
    html += """
        </article>
"""
    
    html += """
    </main>
"""
    html += generate_footer()
    return html


def build_html_docs(json_path: str, output_dir: str):
    """Build all HTML documentation from JSON."""
    print(f"Loading documentation from: {json_path}")
    data = load_documentation(json_path)
    
    constructors = data.get('constructors', [])
    methods = data.get('methods', [])
    
    print(f"Found {len(constructors)} constructors and {len(methods)} methods")
    
    # Build type map: collect all constructors by their result_type
    type_map = {}
    for item in constructors:
        result_type = item.get('result_type', '')
        if result_type and not result_type.startswith('Vector'):
            # Normalize type name (remove any extra spaces)
            result_type = result_type.strip()
            if result_type not in type_map:
                type_map[result_type] = []
            type_map[result_type].append(item)
    
    # Precompute set of Go type names for collision detection
    go_types_set = {to_go_name(t) for t in type_map.keys()}
    print(f"Found {len(type_map)} unique types and {len(go_types_set)} Go type names")
    
    # Build search data once for all pages
    search_data = []
    for item in constructors:
        go_name = to_go_name(item['name'])
        # Add Obj suffix for constructors where name matches a type name
        display_name = go_name + 'Obj' if go_name in go_types_set else go_name
        search_name = display_name.lower() + " " + item['name'].lower().replace('.', ' ')
        # Also include non-Obj version in search for convenience
        if display_name != go_name:
            search_name += " " + go_name.lower()
        search_data.append({
            "name": item['name'],
            "goDisplay": display_name,
            "searchName": search_name,
            "desc": item.get('description', ''),
            "type": "constructor",
            "path": get_output_path(item['name'], 'constructor')
        })
    for item in methods:
        go_name = to_go_name(item['name'])
        search_data.append({
            "name": item['name'],
            "goDisplay": go_name,
            "searchName": go_name.lower() + " " + item['name'].lower().replace('.', ' '),
            "desc": item.get('description', ''),
            "type": "method",
            "path": get_output_path(item['name'], 'method')
        })
    for type_name, ctors in type_map.items():
        go_type = to_go_name(type_name)
        search_data.append({
            "name": type_name,
            "goDisplay": go_type,
            "searchName": go_type.lower() + " " + type_name.lower(),
            "desc": f"Abstract type with {len(ctors)} constructor{'s' if len(ctors) != 1 else ''}",
            "type": "type",
            "path": f"types/{type_name}.html"
        })
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Generate index page
    print("Generating index.html...")
    index_html = generate_index_page(data)
    (output_path / 'index.html').write_text(index_html, encoding='utf-8')
    
    # Save search index to a separate JS file to avoid bloating every page
    print("Generating search_index.js...")
    js_dir = output_path / 'js'
    js_dir.mkdir(parents=True, exist_ok=True)
    search_js_content = f"window.searchData = {json.dumps(search_data)};"
    (js_dir / 'search_index.js').write_text(search_js_content, encoding='utf-8')
    
    # Generate constructors list page
    print("Generating constructors.html...")
    constructors_html = generate_list_page(constructors, 'constructor', 'Constructors', search_data)
    (output_path / 'constructors.html').write_text(constructors_html, encoding='utf-8')
    
    # Generate methods list page
    print("Generating methods.html...")
    methods_html = generate_list_page(methods, 'method', 'Methods', search_data)
    (output_path / 'methods.html').write_text(methods_html, encoding='utf-8')
    
    # Generate types list page
    print("Generating types.html...")
    types_html = generate_types_list_page(type_map, search_data)
    (output_path / 'types.html').write_text(types_html, encoding='utf-8')
    
    # Generate individual type pages
    print("Generating type pages...")
    types_path = output_path / 'types'
    types_path.mkdir(parents=True, exist_ok=True)
    for type_name, type_constructors in type_map.items():
        type_html = generate_type_page(type_name, type_constructors, search_data, type_map)
        (types_path / f'{type_name}.html').write_text(type_html, encoding='utf-8')
    print(f"  Generated {len(type_map)} type pages")
    
    # Generate individual constructor pages
    print("Generating constructor pages...")
    for i, item in enumerate(constructors):
        rel_path = get_output_path(item['name'], 'constructor')
        full_path = output_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        page_html = generate_detail_page(item, 'constructor', search_data, type_map, go_types_set)
        full_path.write_text(page_html, encoding='utf-8')
        
        if (i + 1) % 100 == 0:
            print(f"  Generated {i + 1}/{len(constructors)} constructor pages")
    print(f"  Generated {len(constructors)} constructor pages")
    
    # Generate individual method pages
    print("Generating method pages...")
    for i, item in enumerate(methods):
        rel_path = get_output_path(item['name'], 'method')
        full_path = output_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        page_html = generate_detail_page(item, 'method', search_data, type_map)
        full_path.write_text(page_html, encoding='utf-8')
        
        if (i + 1) % 100 == 0:
            print(f"  Generated {i + 1}/{len(methods)} method pages")
    print(f"  Generated {len(methods)} method pages")
    
    print(f"\nDone! Output written to: {output_dir}")
    print(f"  - index.html")
    print(f"  - constructors.html ({len(constructors)} types)")
    print(f"  - methods.html ({len(methods)} methods)")
    print(f"  - types.html ({len(type_map)} types)")
    print(f"  - constructors/ folder with individual pages")
    print(f"  - methods/ folder with individual pages")
    print(f"  - types/ folder with individual type pages")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Build HTML documentation from TL JSON')
    parser.add_argument('json_file', help='Path to the JSON documentation file')
    parser.add_argument('-o', '--output', default='public', help='Output directory (default: public)')
    
    args = parser.parse_args()
    
    build_html_docs(args.json_file, args.output)


if __name__ == '__main__':
    main()

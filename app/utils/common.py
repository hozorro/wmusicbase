# -*- encoding: utf-8 -*-
'''
@File      :   common.py
@Time      :   2025/11/06 16:26:20
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   common tools
'''


import re
def parse_year(date_str: str) -> int | None:
    '''parse year from date string'''
    if not date_str: return None
    year_str = ''.join(filter(str.isdigit, date_str[:4]))
    return int(year_str) if year_str.isdigit() and len(year_str) == 4 else None
def decode_object(obj, original_encoding):
    '''decode object'''
    if not original_encoding:
        return obj
    if isinstance(obj, bytes):
        return obj.decode('utf-8')
    elif isinstance(obj, dict):
        return {key: decode_object(value, original_encoding) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [decode_object(item, original_encoding) for item in obj]
    else:
        try:
            if obj is None:
                return None
            if not isinstance(obj, str):
                return obj
            if original_encoding == 'utf-8':
                return obj.strip('\x00').strip()
            ret = obj.encode(original_encoding).decode('gb18030').strip('\x00').strip()
            return ret
        except UnicodeDecodeError:
            print(f'UnicodeDecodeError for object: {obj}, trying ignore errors.')
            return obj.encode(original_encoding).decode(original_encoding, errors='ignore').strip('\x00').strip()
        
def parse_multiple_value(value: str) -> list[str] | None:
    '''parse multiple value, return list'''
    sep = r'[;,，&|/\\]'
    return list(map(lambda x: x.strip(), re.split(sep, value))) if value else None

# Invalid folder name characters: < > : " / \ | ? *
_INVALID_CHARS_PATTERN = re.compile(r'[<>:"/\\|?*]')
def sanitize_folder_name(name: str) -> str:
    '''
    sanitize folder name by replacing all invalid characters with '_'
    Windows invalid chars: < > : " / \\ | ? *
    Also handles trailing dots and spaces
    '''
    # replace all invalid characters
    result = _INVALID_CHARS_PATTERN.sub('_', name)
    # replace trailing dots and spaces
    result = re.sub(r'[. ]+$', '_', result)
    return result
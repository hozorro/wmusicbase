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
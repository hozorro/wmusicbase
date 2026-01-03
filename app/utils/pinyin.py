# -*- encoding: utf-8 -*-
'''
@File      :   pinyin.py
@Time      :   2025/10/19 22:37:43
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   pinyin tools
'''


import re
from pypinyin import lazy_pinyin, Style

def normalize_initial(char: str) -> str:
    '''
    get the initial char alphabet of a character string(Chinese or English or others)
    - English letters A-Z -> keep uppercase
    - other (numbers, symbols, non-letters) -> '_'
    '''
    if not char: 
        return '_'
    upper_char = char.upper()
    if re.match(r'^[A-Z]$', upper_char):
        return upper_char
    return '_'

def get_artist_sort_fields(name: str) -> tuple[str, str]:
    '''
    generate sort and group fields from artist name
    Args:
        name (str): artist name
    Returns:
        tuple[str, str]: (sort_name, pinyin_initial)
            - sort_name: sort name for search and order(all string)
            - pinyin_initial: initial alphabet used for group(A-Z or '_')
    '''
    if not name or not name.strip(): 
        return '', '_'
    name = name.strip()
    # use pypinyin lib to get pinyin list(multi-word reserved)
    pinyin_parts = lazy_pinyin(name, style=Style.NORMAL)

    # build sort_name: uppercase of the first alphabet, separated by space
    sort_name = ' '.join(pinyin_parts).title()

    # get the first alphabet
    if pinyin_parts and pinyin_parts[0]: 
        first_pinyin = pinyin_parts[0]
        first_char = first_pinyin[0]
        initial = normalize_initial(first_char)
    else: 
        initial = '_'

    return sort_name, initial
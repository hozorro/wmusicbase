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
    将字符标准化为首字母分组标识。
    - 英文字母A-Z -> 保持大写
    - 其他（数字、符号、非字母） -> '_'
    '''
    if not char: 
        return '_'
    upper_char = char.upper()
    if re.match(r'^[A-Z]$', upper_char):
        return upper_char
    return '_'

def get_artist_sort_fields(name: str) -> tuple[str, str]:
    '''
    从artist原始名称生成用于排序和分组的字段。
    Args:
        name (str): artist原始名称
    Returns:
        tuple[str, str]: (sort_name, pinyin_initial)
            - sort_name: 用于排序的标准化名称（全拼）
            - pinyin_initial: 用于分组的首字母（A-Z或'_'）
    '''
    if not name or not name.strip(): 
        return '', '_'
    name = name.strip()
    # 使用pypinyin获取拼音列表（保留multi-word)
    pinyin_parts = lazy_pinyin(name, style=Style.NORMAL)

    # 构建sort_name: 首字母大写，空格分隔
    sort_name = ' '.join(pinyin_parts).title()

    # 获取首字母
    if pinyin_parts and pinyin_parts[0]: 
        first_pinyin = pinyin_parts[0]
        first_char = first_pinyin[0]
        initial = normalize_initial(first_char)
    else: 
        initial = '_'

    return sort_name, initial
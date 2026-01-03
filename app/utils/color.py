# -*- encoding: utf-8 -*-
'''
@File      :   color.py
@Time      :   2025/10/20 11:21:42
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   color tools
'''


import random, math

def generate_unique_light_color(existing_colors: set, step=16) -> str:
    '''
    generate a unique light color
    - step: color step, default 16, control the difference, 
    maybe conflict if the number is too big, total color count is (256 / step / 2) ^ 3
    '''
    end = math.floor(256 / step)
    start = math.floor(end / 2)
    max_attempts = 100
    for _ in range(max_attempts):
        r = random.randint(start, end) * step - 1
        g = random.randint(start, end) * step - 1
        b = random.randint(start, end) * step - 1
        color = f'#{r:02x}{g:02x}{b:02x}'
        if color not in existing_colors: # ensure the color is unique
            return color
    return '#7f7f7f' # if all attempts fail, return a default color
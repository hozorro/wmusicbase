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
    生成一个唯一的浅色颜色
    - step: 颜色步长，默认为16，控制差异度，过大可能导致颜色冲突，颜色总数为(256 / step / 2) ^ 3
    '''
    end = math.floor(256 / step)
    start = math.floor(end / 2)
    max_attempts = 100
    for _ in range(max_attempts):
        r = random.randint(start, end) * step - 1
        g = random.randint(start, end) * step - 1
        b = random.randint(start, end) * step - 1
        color = f'#{r:02x}{g:02x}{b:02x}'
        if color not in existing_colors: # 确保颜色不重复
            return color
    return '#7f7f7f' # 如果尝试次数过多，则返回默认颜色
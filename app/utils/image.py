# -*- encoding: utf-8 -*-
'''
@File      :   image.py
@Time      :   2026/03/08 16:19:37
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2026 WEYECO <enauvy@qq.com>
@Desc      :   image tools
'''


from PIL import Image
from io import BytesIO

def resize_image(img_data: bytes, max_width: int = 512) -> bytes:
    """
    Resize an image to a maximum width while maintaining aspect ratio.

    Args:
        img_data (bytes): The image data as bytes.
        max_width (int, optional): The maximum width of the resized image. Defaults to 512.

    Returns:
        bytes: The resized image data as bytes.
    """
    img_byte_arr = None
    with Image.open(BytesIO(img_data)) as img:
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        img_byte_arr = BytesIO()
        img.convert('RGB').save(img_byte_arr, format='JPEG', quality=90)
        img_byte_arr = img_byte_arr.getvalue()

    return img_byte_arr
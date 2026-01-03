# -*- encoding: utf-8 -*-
'''
@File      :   signer.py
@Time      :   2025/12/23 11:25:33
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   create signed url or other things
'''


from itsdangerous import TimestampSigner
from app.core.config import settings

signer = TimestampSigner(settings.SECRET_KEY)
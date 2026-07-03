# -*- encoding: utf-8 -*-
'''
@File      :   __init__.py
@Desc      :   Auto-import all check modules to trigger @register_check and @register_after_check decorators
'''


# import all check modules to trigger registration
from . import metadata_checks    # noqa: F401
from . import artwork_checks     # noqa: F401
from . import structure_checks   # noqa: F401
from . import encoding_checks    # noqa: F401
from . import duplicate_checks   # noqa: F401

from .base import (
    BaseCheck, Issue,
    register_check, get_all_checks,
    register_after_check, get_all_after_checks,
)

__all__ = [
    'BaseCheck', 'Issue',
    'register_check', 'get_all_checks',
    'register_after_check', 'get_all_after_checks',
]

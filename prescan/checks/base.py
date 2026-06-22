# -*- encoding: utf-8 -*-
'''
@File      :   base.py
@Desc      :   Check framework base class and registry
'''


from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from pathlib import Path
from sqlalchemy.orm import Session


@dataclass
class Issue:
    check_name: str
    severity: str          # 'error' | 'warning' | 'info'
    entity_type: str       # 'track' | 'artist' | 'album' | 'directory'
    entity_id: int | None
    file_path: str | None
    message: str
    detail: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class BaseCheck(ABC):
    '''abstract base class for all inspection checks'''

    name: str              # unique check identifier, e.g. 'missing_title'
    description: str       # human-readable description

    def __init__(self, session: Session, library_path: Path):
        self.session = session
        self.library_path = library_path

    @abstractmethod
    def run(self) -> list[Issue]:
        '''execute the check, return a list of Issues'''
        ...


# ==================== Registry ====================

_check_registry: list[type[BaseCheck]] = []


def register_check(cls: type[BaseCheck]) -> type[BaseCheck]:
    '''decorator: register a check class'''
    _check_registry.append(cls)
    return cls


def get_all_checks() -> list[type[BaseCheck]]:
    '''return all registered check classes'''
    return list(_check_registry)

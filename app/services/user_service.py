# -*- encoding: utf-8 -*-
'''
@File      :   user_service.py
@Time      :   2025/12/01 19:09:55
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   user service
'''


from sqlalchemy import select
from app.core.deps import DbDep
from app.models.user import User

class UserService:
    def __init__(self, db: DbDep):
        self.db = db

    async def get_user(self, user_id: int) -> dict | None:
        user = await self.db.get(User, user_id)
        if user:
            return {'id': user.id, 'username': user.username, 'last_login_at': user.last_login_at.strftime('%Y-%m-%d %H:%M:%S')}
        return None
    
    async def get_user_list(self) -> list[dict]:
        result = await self.db.execute(select(User))
        return [{
            'id': user.id, 
            'username': user.username,
            'last_login_at': user.last_login_at.strftime('%Y-%m-%d %H:%M:%S') if user.last_login_at else user.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for user in result.scalars().all()]
    
    async def search_user(self, keyword: str) -> list[dict]:
        result = await self.db.execute(
            select(User)
            .where(User.username.like(f'%{keyword}%'))
        )
        return [{'id': user.id, 'username': user.username} for user in result.scalars().all()]
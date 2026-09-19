# -*- encoding: utf-8 -*-
'''
@File      :   user_service.py
@Time      :   2025/12/01 19:09:55
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   user service
'''


from sqlalchemy import select, func
from app.core.deps import DbDep
from app.models import UserToken
from app.models.user import User

class UserService:
    def __init__(self, db: DbDep):
        self.db = db

    async def get_user(self, user_id: int) -> dict | None:
        user = await self.db.get(User, user_id)
        if user:
            return {'id': user.id, 'username': user.username, 'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S')}
        return None
    
    async def get_user_list(self) -> list[dict]:
        token_ranked = (
            select(
                UserToken.user_id,
                UserToken.client_type,
                UserToken.device_id,
                UserToken.last_used_at,
                func.row_number().over(
                    partition_by=UserToken.user_id,
                    order_by=UserToken.last_used_at.desc().nullslast()
                ).label('rn')
            ).where(UserToken.last_used_at.isnot(None))
            .subquery()
        )
        stmt = (
            select(
                User,
                token_ranked.c.client_type,
                token_ranked.c.device_id,
                token_ranked.c.last_used_at
            ).outerjoin(
                token_ranked,
                (token_ranked.c.user_id == User.id) & (token_ranked.c.rn == 1)
            )
        )
        result = await self.db.execute(stmt)
        user_list = []
        if result:
            user_list = [{
                "id": user.id, 
                "username": user.username, 
                "is_admin": user.is_admin, 
                "client_type": client_type,
                "device_id": device_id,
                "last_login_at": last_used_at
            } for user, client_type, device_id, last_used_at in result.all()]
        return user_list
    
    async def search_user(self, keyword: str) -> list[dict]:
        result = await self.db.execute(
            select(User)
            .where(User.username.like(f'%{keyword}%'))
        )
        return [{'id': user.id, 'username': user.username} for user in result.scalars().all()]
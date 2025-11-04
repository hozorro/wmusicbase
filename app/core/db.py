from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from .config import settings
from typing import AsyncGenerator

engine = create_async_engine(
    str(settings.DATABASE_URL), 
    echo=False,    # print sql when debug
    pool_pre_ping=True,     # check connection when get session
    pool_size=20,           # max connection pool size
    max_overflow=10,        # max connection overflow
    future=True,            # use asyncio
)

AsyncSessionLocal = sessionmaker(
    bind=engine, 
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# FastAPI dependency injection: used for get db session in each request route
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    '''
    依赖注入函数，供FastAPI路由使用。
    自动管理会话生命周期：开启->提交/回滚->关闭。
    '''
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except:
            await session.rollback()
            raise

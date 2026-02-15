import asyncio
from functools import wraps
from app.core.logger import logger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from asyncpg.exceptions import DeadlockDetectedError, InFailedSQLTransactionError
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

AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# FastAPI dependency injection: used for get db session in each request route
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    '''
    Depend function, for FastAPI route dependency of getting db session.
    Manage session lifecycle by itself: open->commit/rollback->->close
    '''
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except:
            await session.rollback()
            raise
        finally:
            await session.close()

# deadlock retry decorator
def retry_deadlock(max_retries: int = 3, delay: float = 0.1):
    '''
    async deadlock retry decorator: retry when deadlock detected, avoid failure due to single deadlock.
    :param max_retries: max retries
    :param delay: delay time of each retry
    '''
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return await func(*args, **kwargs)
                except (DeadlockDetectedError) as e:
                    retries += 1
                    wait_time = delay * (2 ** retries)  # delay with exponential backoff
                    logger.warning(f'Deadlock detected in {func.__name__}, retrying {retries}/{max_retries} after {wait_time}s: {str(e)}')
                    await asyncio.sleep(wait_time)
                    if retries >= max_retries:
                        logger.error(f'Max retries reached for {func.__name__} due to deadlock: {str(e)}')
                        raise
                except InFailedSQLTransactionError as e:
                    # transaction interrupted: force rollback and retry
                    retries += 1
                    logger.warning(f'InFailedSQLTransactionError in {func.__name__}, retrying {retries}/{max_retries}: {str(e)}')
                    # try to get session and rollback
                    session = next((arg for arg in args if isinstance(arg, AsyncSession)), None)
                    if session and not session.is_closed():
                        await session.rollback()
                    await asyncio.sleep(delay * retries)
                    if retries >= max_retries:
                        logger.error(f'Max retries reached for {func.__name__} due to InFailedSQLTransactionError: {str(e)}')
                        raise
            return None
        return wrapper
    return decorator

# safe transaction
async def safe_async_transaction(session: AsyncSession, func, *args, **kwargs):
    '''
    excute async transaction safely, automatically handle transaction interruption and deadlock.
    :param session: session for excute async transaction
    :param func: async function to be excuted in transaction
    :param args: arguments for func
    :param kwargs: keyword arguments for func
    '''
    try:
        result = await func(*args, **kwargs)
        await session.commit()
        return result
    except (DeadlockDetectedError, InFailedSQLTransactionError) as e:
        await session.rollback()
        logger.error(f"❌transaction handle error and rollback: {str(e)}")
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"❌failed due to unknown error and rollback: {str(e)}", exc_info=True)
        raise
    finally:
        # ensure session closed
        if session.is_active:
            await session.close()
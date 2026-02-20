"""
Database connection and Beanie ODM initialization.

Beanie is an async ODM for MongoDB built on Motor and Pydantic.
We initialize it once at startup and close at shutdown.
"""

import logging
from typing import List, Type

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings
from app.models.document import Document
from app.models.timeline import Timeline
from app.models.user import User

logger = logging.getLogger(__name__)


async def connect_to_mongo() -> None:
    """
    Create Motor client and initialize Beanie with document models.
    Called once at application startup.
    """
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_url)
    database = client[settings.mongodb_database]

    # Document models that Beanie will manage (collections + indexes)
    document_models: List[Type] = [User, Document, Timeline]

    await init_beanie(
        database=database,
        document_models=document_models,
    )
    logger.info("MongoDB connection established; Beanie initialized.")


async def close_mongo_connection() -> None:
    """
    Close MongoDB connection on application shutdown.
    Motor client is stored in Beanie's internal state; we log only here.
    In production you might get client from app.state if you stored it.
    """
    logger.info("Closing MongoDB connection.")
    # Motor doesn't require explicit close in most cases; connection pool is cleaned up.
    # If you stored the client in app.state, you would call client.close() here.
    pass

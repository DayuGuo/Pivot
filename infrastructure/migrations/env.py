from alembic import context
from sqlalchemy import create_engine, pool

from apps.api.publishing import editorial_chat, editorial_demo  # noqa: F401
from apps.api.publishing.db import DATABASE_URL
from apps.api.publishing.domain import checks as publishing_checks  # noqa: F401
from apps.api.publishing.domain import models as publishing_models  # noqa: F401
from apps.api.publishing.models import Base

if context.is_offline_mode():
    context.configure(url=DATABASE_URL, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()

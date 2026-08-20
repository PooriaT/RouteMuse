"""Enable PostGIS."""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def downgrade() -> None:
    # Keep the extension installed: later geospatial objects may depend on it, and
    # dropping it (especially with CASCADE) risks destructive data loss.
    pass

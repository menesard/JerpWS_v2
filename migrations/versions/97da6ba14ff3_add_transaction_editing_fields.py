"""Add transaction editing fields

Revision ID: transaction_editing_fields
Revises: pure_gold_calculations
Create Date: 2025-03-11 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'transaction_editing_fields'
down_revision = 'pure_gold_calculations'
branch_labels = None
depends_on = None


def upgrade():
    # CustomerTransaction tablosuna düzenleme alanları ekle
    op.add_column('customer_transactions', sa.Column('is_edited', sa.Boolean(), nullable=True, default=False))
    op.add_column('customer_transactions', sa.Column('edited_date', sa.DateTime(), nullable=True))
    op.add_column('customer_transactions', sa.Column('edited_by_user_id', sa.Integer(), nullable=True))
    op.add_column('customer_transactions', sa.Column('original_transaction_id', sa.Integer(), nullable=True))

    # Foreign key oluştur
    op.create_foreign_key('fk_edited_by_user', 'customer_transactions', 'users',
                         ['edited_by_user_id'], ['id'])
    op.create_foreign_key('fk_original_transaction', 'customer_transactions', 'customer_transactions',
                         ['original_transaction_id'], ['id'])


def downgrade():
    # Foreign key'leri kaldır
    op.drop_constraint('fk_edited_by_user', 'customer_transactions', type_='foreignkey')
    op.drop_constraint('fk_original_transaction', 'customer_transactions', type_='foreignkey')

    # Alanları kaldır
    op.drop_column('customer_transactions', 'original_transaction_id')
    op.drop_column('customer_transactions', 'edited_by_user_id')
    op.drop_column('customer_transactions', 'edited_date')
    op.drop_column('customer_transactions', 'is_edited')
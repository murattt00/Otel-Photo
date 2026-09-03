"""siparis paket ve teslim zamani + status index

Revision ID: a1b7c4d90e21
Revises: f52b342ba005
Create Date: 2026-09-03 17:05:00.000000

Neden:
- packaged_at : gonderim zip'inin en son ne zaman hazirlandigi. Eskiden paketin varligi
                sadece diskteki zip dosyasindan okunuyordu; operator zip'i alip gonderince
                (klasorden tasiyinca) sistem "hic paketlenmemis" saniyordu.
- delivered_at: operatorun "Gonderildi" dedigi an. status='teslim' gecisi hicbir yerde
                yapilmiyordu, dongu kapanmiyordu.
- orders.status uzerine index: panel her sekmede status'e gore filtreliyor + /orders/sayilar
  status'e gore grupluyor.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b7c4d90e21'
down_revision: Union[str, Sequence[str], None] = 'f52b342ba005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('orders', sa.Column('packaged_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('orders', sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_orders_status'), 'orders', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_orders_status'), table_name='orders')
    op.drop_column('orders', 'delivered_at')
    op.drop_column('orders', 'packaged_at')

import asyncio
import unittest
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.models.media_port_lease import MediaPortLease
from app.core.media_nodes_db import RuntimeMediaNode, allocate_rtp_port_with_lease


class TestMediaPortAllocation(unittest.TestCase):
    def test_allocate_with_start_from_and_exclude(self):
        async def _run():
            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            Session = async_sessionmaker(engine, expire_on_commit=False)
            node = RuntimeMediaNode(
                id="node1",
                host="127.0.0.1",
                http_port=8880,
                rtp_port=30000,
                public_host="127.0.0.1",
                public_http_port=8880,
                secret="s",
                rtp_port_mode="range",
                rtp_port_range_start=30000,
                rtp_port_range_end=30002,
            )

            # allocate_rtp_port_with_lease deliberately uses random.randint to
            # pick a starting offset (concurrency anti-storm). Patch it to 0 so
            # the allocation order is deterministic: 30000 -> 30001 -> 30002.
            with patch("random.randint", return_value=0):
                async with Session() as db:
                    port, lease_id = await allocate_rtp_port_with_lease(db, node, exclude_ports={30000})
                    self.assertEqual(port, 30001)
                    self.assertIsNotNone(lease_id)

                    await db.commit()

                async with Session() as db:
                    port2, lease_id2 = await allocate_rtp_port_with_lease(db, node, start_from=30002)
                    self.assertEqual(port2, 30002)
                    self.assertIsNotNone(lease_id2)

                    await db.commit()

            async with Session() as db:
                cnt = await db.scalar(select(func.count()).select_from(MediaPortLease))
                self.assertEqual(cnt, 2)

            await engine.dispose()

        asyncio.run(_run())

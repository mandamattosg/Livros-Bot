import unittest
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.worker_lock import WorkerLock
from app.scheduler.worker_lock import WorkerLockService
from app.utils.datetime_utc import utc_now


class WorkerLockServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.session = self.Session()
        self.service = WorkerLockService(self.session)

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def test_acquire_blocks_second_owner_until_expiration(self) -> None:
        self.assertTrue(self.service.acquire("notification_worker", "owner-a", 60))
        self.assertFalse(self.service.acquire("notification_worker", "owner-b", 60))

    def test_expired_lock_can_be_reacquired(self) -> None:
        self.assertTrue(self.service.acquire("monitoring_worker", "owner-a", 60))
        lock = self.session.query(WorkerLock).filter(WorkerLock.worker_name == "monitoring_worker").first()
        lock.expires_at = utc_now() - timedelta(seconds=1)
        self.session.commit()

        self.assertTrue(self.service.acquire("monitoring_worker", "owner-b", 60))
        self.session.refresh(lock)
        self.assertEqual(lock.owner_id, "owner-b")
        self.assertGreater(lock.expires_at, utc_now().replace(tzinfo=None))
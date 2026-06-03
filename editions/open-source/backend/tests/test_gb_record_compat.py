import types
import unittest


class TestGbRecordCompat(unittest.IsolatedAsyncioTestCase):
    async def test_query_start_progress_stop_contract(self):
        from app.api.v1.endpoints import gb_record as gb_record_ep

        current_user = types.SimpleNamespace(
            tenant_id="default",
            is_superuser=False,
            username="tester",
        )
        fake_db = object()

        original_query = gb_record_ep.device_record_ep.query_device_records
        original_start = gb_record_ep.device_record_ep.start_device_record_download
        original_progress = gb_record_ep.device_record_ep.get_device_record_download_progress
        original_stop = gb_record_ep.device_record_ep.stop_device_record_download
        original_find_task = gb_record_ep._find_download_task_by_stream

        async def fake_query_records(**kwargs):
            return [
                {"start_time": "2026-04-01T01:00:00+00:00", "end_time": "2026-04-01T01:10:00+00:00", "type": "all"},
                {"start_time": "2026-04-01T02:00:00+00:00", "end_time": "2026-04-01T02:20:00+00:00", "type": "manual"},
            ]

        async def fake_start_download(*, payload, db, current_user):
            self.assertEqual(payload.device_id, "34020000001320000001")
            self.assertEqual(payload.channel_id, "34020000001320000001")
            return {
                "task_id": "task-1",
                "status": "pending",
                "app": "playback",
                "stream": "stream-1",
            }

        async def fake_progress_download(*, task_id, auto_stop, db, current_user):
            self.assertEqual(task_id, "task-1")
            self.assertTrue(auto_stop)
            return {
                "task_id": "task-1",
                "status": "running",
                "app": "playback",
                "stream": "stream-1",
                "percent": 37,
                "records": [{"record_id": "r1", "download_url": "/api/v1/record/download/r1"}],
                "recorded_seconds": 111,
                "total_seconds": 300,
                "last_error": "",
            }

        async def fake_stop_download(*, task_id, db, current_user):
            self.assertEqual(task_id, "task-1")
            return {"ok": True, "task_id": "task-1", "status": "cancelled"}

        async def fake_find_task_by_stream(db, **kwargs):
            return types.SimpleNamespace(id="task-1")

        gb_record_ep.device_record_ep.query_device_records = fake_query_records
        gb_record_ep.device_record_ep.start_device_record_download = fake_start_download
        gb_record_ep.device_record_ep.get_device_record_download_progress = fake_progress_download
        gb_record_ep.device_record_ep.stop_device_record_download = fake_stop_download
        gb_record_ep._find_download_task_by_stream = fake_find_task_by_stream

        try:
            query_res = await gb_record_ep.query_record_compat(
                device_id="34020000001320000001",
                channel_id="34020000001320000001",
                startTime="2026-04-01 00:00:00",
                endTime="2026-04-01 23:59:59",
                db=fake_db,
                current_user=current_user,
            )
            self.assertEqual(query_res["code"], 0)
            self.assertEqual(query_res["data"]["sumNum"], 2)
            self.assertEqual(len(query_res["data"]["recordList"]), 2)

            start_res = await gb_record_ep.start_download_compat(
                device_id="34020000001320000001",
                channel_id="34020000001320000001",
                startTime="2026-04-01 01:00:00",
                endTime="2026-04-01 01:10:00",
                downloadSpeed=4,
                db=fake_db,
                current_user=current_user,
            )
            self.assertEqual(start_res["code"], 0)
            self.assertEqual(start_res["data"]["stream"], "stream-1")
            self.assertEqual(start_res["data"]["downloadSpeed"], 4)

            progress_res = await gb_record_ep.progress_download_compat(
                device_id="34020000001320000001",
                channel_id="34020000001320000001",
                stream="stream-1",
                db=fake_db,
                current_user=current_user,
            )
            self.assertEqual(progress_res["code"], 0)
            self.assertEqual(progress_res["data"]["progress"], 37)
            self.assertEqual(len(progress_res["data"]["records"]), 1)

            stop_res = await gb_record_ep.stop_download_compat(
                device_id="34020000001320000001",
                channel_id="34020000001320000001",
                stream="stream-1",
                db=fake_db,
                current_user=current_user,
            )
            self.assertEqual(stop_res["code"], 0)
            self.assertEqual(stop_res["data"]["status"], "cancelled")
        finally:
            gb_record_ep.device_record_ep.query_device_records = original_query
            gb_record_ep.device_record_ep.start_device_record_download = original_start
            gb_record_ep.device_record_ep.get_device_record_download_progress = original_progress
            gb_record_ep.device_record_ep.stop_device_record_download = original_stop
            gb_record_ep._find_download_task_by_stream = original_find_task


if __name__ == "__main__":
    unittest.main()

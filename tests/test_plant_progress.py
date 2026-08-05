import inspect
import unittest
from unittest.mock import patch

from Game_main.g9_yaoyuan import (
    _record_successful_plant,
    bo_zhong,
    yj_bozhong,
)


class PlantProgressTests(unittest.IsolatedAsyncioTestCase):
    async def test_plant_records_onboarding_and_daily_progress(self):
        with (
            patch("Game_main.g16_onboarding.record_onboarding_event") as onboarding,
            patch("Game_main.g25_daily_tasks.record_daily_event") as daily,
        ):
            await _record_successful_plant(10001)

        onboarding.assert_awaited_once_with(10001, "FARM")
        daily.assert_awaited_once_with(10001, "FARM")

    def test_single_and_one_click_plant_use_shared_progress_hook(self):
        single_source = inspect.getsource(bo_zhong.__wrapped__)
        batch_source = inspect.getsource(yj_bozhong.__wrapped__)
        self.assertIn("await _record_successful_plant(uid)", single_source)
        self.assertIn("await _record_successful_plant(uid)", batch_source)


if __name__ == "__main__":
    unittest.main()

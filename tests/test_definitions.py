def test_definitions_load_with_sp500():
    # Loading defs validates the partitioned form4 job no longer selects '*'
    # (which would illegally include the unpartitioned sp500 asset).
    from edgar_pipeline.definitions import daily, defs

    assert daily.start.date().isoformat() == "2024-07-22"
    schedules = {s.name for s in defs.schedules}
    assert schedules == {
        "form4_daily_schedule",
        "sp500_daily_schedule",
        "dashboard_nightly_schedule",
    }
    assert defs.get_assets_def("sp500_parquet") is not None


def test_form4_schedule_requests_same_day_partition():
    # A plain ScheduleDefinition on a partitioned asset job launches a
    # partition-less run ("Cannot access partition_key for a non-partitioned
    # run" — first observed on the schedule's first real tick, 2026-07-21).
    # The schedule must explicitly request the tick-day's partition.
    import datetime as dt
    from zoneinfo import ZoneInfo

    from dagster import build_schedule_context

    from edgar_pipeline.definitions import defs, form4_daily_schedule

    ctx = build_schedule_context(
        scheduled_execution_time=dt.datetime(2026, 7, 20, 22, 30, tzinfo=ZoneInfo("US/Eastern")),
        repository_def=defs.get_repository_def(),
    )
    result = form4_daily_schedule.evaluate_tick(ctx)
    assert [r.partition_key for r in result.run_requests] == ["2026-07-20"]

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

import pytest

from app.services import aqi
from app.services.air_quality import UpstreamError, build_snapshot
from tests.conftest import make_air_payload, make_weather_payload


@pytest.mark.parametrize("conc,expected", [(0, 0), (30, 50), (45, 76), (60, 100), (90, 200), (250, 400), (900, 500)])
def test_pm25_sub_index_breakpoints(conc, expected):
    assert aqi.sub_index("pm2_5", conc) == expected


def test_sub_index_rejects_bad_input():
    assert aqi.sub_index("pm2_5", None) is None
    assert aqi.sub_index("pm2_5", -1) is None
    assert aqi.sub_index("unknown", 10) is None


def test_naqi_needs_three_pollutants_including_pm():
    assert aqi.naqi({"pm2_5": 50, "pm10": 80})[0] is None
    assert aqi.naqi({"ozone": 50, "nitrogen_dioxide": 50, "sulphur_dioxide": 50})[0] is None
    value, dominant, subs = aqi.naqi({"pm2_5": 95, "pm10": 120, "nitrogen_dioxide": 30})
    assert dominant == "pm2_5" and value == subs["pm2_5"] > 200


@pytest.mark.parametrize("value,key", [(10, "good"), (100, "satisfactory"), (150, "moderate"), (250, "poor"),
                                       (350, "very_poor"), (450, "severe"), (None, "good")])
def test_category(value, key):
    assert aqi.category_for_aqi(value).key == key


def test_snapshot_uses_24h_average_and_labels_source():
    snap = build_snapshot(make_air_payload(), make_weather_payload())
    assert snap["observed_at"] == "2026-11-19T14:00"
    assert snap["aqi"]["value"] is not None and snap["aqi"]["dominant"] == "PM2.5"
    assert snap["source"]["kind"] == "model_estimate"
    assert snap["pollutants_now"]["CO"] == pytest.approx(1.2)  # µg/m³ → mg/m³


def test_snapshot_explains_smog_drivers():
    keys = {d["key"] for d in build_snapshot(make_air_payload(), make_weather_payload())["smog_drivers"]}
    assert {"low_wind", "low_mixing", "fog"} <= keys


def test_best_window_is_afternoon_and_worst_is_rush_hour():
    w = build_snapshot(make_air_payload(), None)["windows"][0]
    assert 12 <= int(w["best"]["start"][11:13]) <= 15
    assert int(w["worst"]["start"][11:13]) in (19, 20)


def test_snapshot_without_hourly_data_raises():
    with pytest.raises(UpstreamError):
        build_snapshot({"hourly": {}}, None)

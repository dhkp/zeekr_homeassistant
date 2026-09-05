import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.zeekr_ev.const import DOMAIN
from custom_components.zeekr_ev.sensor import (
    ZeekrAPIStatusSensor,
    ZeekrChargingTimeFormattedSensor,
    ZeekrEngineStatusSensor,
    ZeekrJourneyLogSensor,
    ZeekrSensor,
    ZeekrVehicleStatusSensor,
    _journey_last_duration,
    _latest_journey_trip,
    async_setup_entry,
)


class DummyCoordinator:
    def __init__(self, data):
        self.data = data


def test_native_value_none_when_no_data():
    coordinator = DummyCoordinator({})
    s = ZeekrSensor(coordinator, "VIN1", "battery_level", "Battery", lambda d: 1, "%")
    assert s.native_value is None


def test_native_value_returns_value():
    data = {
        "VIN1": {
            "additionalVehicleStatus": {"electricVehicleStatus": {"chargeLevel": 42}}
        }
    }
    coordinator = DummyCoordinator(data)
    s = ZeekrSensor(
        coordinator,
        "VIN1",
        "battery_level",
        "Battery",
        lambda d: d.get("additionalVehicleStatus", {}).get("electricVehicleStatus", {}).get("chargeLevel"),
        "%",
    )
    assert s.native_value == 42


def test_numeric_sensor_converts_api_strings_and_rejects_sentinels():
    coordinator = DummyCoordinator({"VIN1": {"value": "13.15"}})
    sensor = ZeekrSensor(
        coordinator,
        "VIN1",
        "numeric",
        "Numeric",
        lambda data: data["value"],
        "V",
        numeric=True,
    )
    assert sensor.native_value == 13.15
    coordinator.data["VIN1"]["value"] = ""
    assert sensor.native_value is None
    coordinator.data["VIN1"]["value"] = "not-a-number"
    assert sensor.native_value is None


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_numeric_sensor_rejects_non_finite_values(value):
    coordinator = DummyCoordinator({"VIN1": {"value": value}})
    sensor = ZeekrSensor(
        coordinator,
        "VIN1",
        "numeric",
        "Numeric",
        lambda data: data["value"],
        numeric=True,
    )

    assert sensor.native_value is None


def test_timestamp_sensor_reports_source_staleness():
    old = datetime.now(timezone.utc) - timedelta(hours=3)
    coordinator = DummyCoordinator({"VIN1": {"updated": old}})
    sensor = ZeekrSensor(
        coordinator,
        "VIN1",
        "updated",
        "Updated",
        lambda data: data["updated"],
        None,
        SensorDeviceClass.TIMESTAMP,
        None,
    )
    attributes = sensor.extra_state_attributes
    assert attributes["source_data_stale"] is True
    assert attributes["source_age_seconds"] >= 3 * 60 * 60


def test_charging_voltage_sensor():
    data = {
        "VIN1": {
            "chargingStatus": {"chargeVoltage": "222.0"}
        }
    }
    coordinator = DummyCoordinator(data)
    s = ZeekrSensor(
        coordinator,
        "VIN1",
        "charge_voltage",
        "Charge Voltage",
        lambda d: d.get("chargingStatus", {}).get("chargeVoltage"),
        "V",
    )
    assert s.native_value == "222.0"


def test_charging_current_sensor():
    data = {
        "VIN1": {
            "chargingStatus": {"chargeCurrent": "9.4"}
        }
    }
    coordinator = DummyCoordinator(data)
    s = ZeekrSensor(
        coordinator,
        "VIN1",
        "charge_current",
        "Charge Current",
        lambda d: d.get("chargingStatus", {}).get("chargeCurrent"),
        "A",
    )
    assert s.native_value == "9.4"


def test_charge_power_sensor():
    data = {
        "VIN1": {
            "chargingStatus": {"chargePower": "2.1"}
        }
    }
    coordinator = DummyCoordinator(data)
    s = ZeekrSensor(
        coordinator,
        "VIN1",
        "charge_power",
        "Charge Power",
        lambda d: d.get("chargingStatus", {}).get("chargePower"),
        "kW",
    )
    assert s.native_value == "2.1"


def test_charger_state_sensor():
    data = {
        "VIN1": {
            "chargingStatus": {"chargerState": "2"}
        }
    }
    coordinator = DummyCoordinator(data)
    s = ZeekrSensor(
        coordinator,
        "VIN1",
        "charger_state",
        "Charger State",
        lambda d: d.get("chargingStatus", {}).get("chargerState"),
    )
    assert s.native_value == "2"


def test_tire_temp_sensors():
    data = {
        "VIN1": {
            "additionalVehicleStatus": {
                "maintenanceStatus": {
                    "tyreTempDriver": 20,
                    "tyreTempPassenger": 21,
                    "tyreTempDriverRear": 22,
                    "tyreTempPassengerRear": 23,
                }
            }
        }
    }
    coordinator = DummyCoordinator(data)

    for tire, val in [("Driver", 20), ("Passenger", 21), ("DriverRear", 22), ("PassengerRear", 23)]:
        s = ZeekrSensor(
            coordinator,
            "VIN1",
            f"tire_temperature_{tire.lower()}",
            f"Tire Temperature {tire}",
            lambda d, t=tire: d.get("additionalVehicleStatus", {})
            .get("maintenanceStatus", {})
            .get(f"tyreTemp{t}"),
            "°C",
        )
        assert s.native_value == val


def test_window_sensors():
    data = {
        "VIN1": {
            "additionalVehicleStatus": {
                "climateStatus": {
                    "winStatusDriver": "2",
                    "winStatusPassenger": "2",
                    "winStatusDriverRear": "2",
                    "winStatusPassengerRear": "2",
                    "winPosDriver": "0",
                    "winPosPassenger": "0",
                    "winPosDriverRear": "0",
                    "winPosPassengerRear": "0",
                }
            }
        }
    }
    coordinator = DummyCoordinator(data)

    # Status
    for win, status in [("Driver", "2"), ("Passenger", "2"), ("DriverRear", "2"), ("PassengerRear", "2")]:
        s = ZeekrSensor(
            coordinator,
            "VIN1",
            f"window_status_{win.lower()}",
            f"Window Status {win}",
            lambda d, w=win: d.get("additionalVehicleStatus", {})
            .get("climateStatus", {})
            .get(f"winStatus{w}"),
            None,
        )
        assert s.native_value == status

    # Position
    for win, pos in [("Driver", "0"), ("Passenger", "0"), ("DriverRear", "0"), ("PassengerRear", "0")]:
        s = ZeekrSensor(
            coordinator,
            "VIN1",
            f"window_position_{win.lower()}",
            f"Window Position {win}",
            lambda d, w=win: d.get("additionalVehicleStatus", {})
            .get("climateStatus", {})
            .get(f"winPos{w}"),
            "%",
        )
        assert s.native_value == pos


@pytest.mark.asyncio
async def test_setup_adds_zeekr_x_telemetry_and_freshness_sensors():
    data = {
        "VIN1": {
            "updateTime": 1788582040345,
            "basicVehicleStatus": {"speed": "0"},
            "chargingStatus": {
                "chargeVoltage": "230.5",
                "chargeCurrent": "15.8",
                "chargePower": "3.6",
                "chargeSpeed": "22.4",
                "updateTime": 1788582040345,
            },
            "chargePlan": {"updateTime": 1788533152908},
            "travelPlan": {"updateTime": 1788533152994},
            "additionalVehicleStatus": {
                "electricVehicleStatus": {
                    "chargeLevel": "100.0",
                    "distanceToEmptyOnBatteryOnly": "333",
                },
                "climateStatus": {
                    "interiorTemp": "16.3",
                    "updateTime": 1788582040345,
                },
                "runningStatus": {"tripMeter1": "9850.6"},
                "remoteControlState": {
                    "overheatState": "1",
                    "parkingComfortState": "1",
                },
                "maintenanceStatus": {
                    "odometer": "17134",
                    "tyreStatusDriver": "258",
                    "tyreTempDriver": "20",
                    "distanceToService": 22879,
                    "daysToService": 489,
                    "mainBatteryStatus": {"voltage": 13.15},
                },
            },
        }
    }
    coordinator = DummyCoordinator(data)
    coordinator.client = MagicMock()
    coordinator.vehicles = []
    coordinator.request_stats = None
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {}
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator}}
    add_entities = MagicMock()

    await async_setup_entry(hass, entry, add_entities)

    entities = {
        entity.key: entity
        for entity in add_entities.call_args[0][0]
        if isinstance(entity, ZeekrSensor)
    }
    assert entities["trip_1_distance"].native_value == 9850.6
    assert entities["trip_1_distance"].state_class == SensorStateClass.MEASUREMENT
    assert entities["distance_to_service"].native_value == 22879
    assert entities["days_to_service"].native_value == 489
    assert entities["battery_12v_voltage"].native_value == 13.15
    assert entities["vehicle_speed"].native_value == 0
    assert entities["cabin_overheat_protection_state"].native_value == "1"
    assert entities["parking_comfort_state"].native_value == "1"
    assert entities["battery_level"].native_value == 100.0
    assert entities["range"].native_value == 333.0
    assert entities["interior_temp"].native_value == 16.3
    assert entities["odometer"].native_value == 17134.0
    assert entities["tire_pressure_driver"].native_value == 258.0
    assert entities["tire_temperature_driver"].native_value == 20.0
    assert entities["charge_voltage"].native_value == 230.5
    assert entities["charge_current"].native_value == 15.8
    assert entities["charge_power"].native_value == 3.6
    assert entities["charge_speed"].native_value == 22.4
    assert "distance_to_empty_on_battery_20_soc" not in entities
    assert "distance_to_empty_on_battery_100_soc" not in entities
    assert {
        "data_last_updated",
        "climate_data_last_updated",
        "charging_data_last_updated",
        "charge_plan_last_updated",
        "travel_plan_last_updated",
    } <= entities.keys()
    assert entities["data_last_updated"].native_value == datetime(
        2026, 9, 5, 4, 20, 40, 345000, tzinfo=timezone.utc
    )


def test_vehicle_status_sensor():
    """Test ZeekrVehicleStatusSensor maps usageMode correctly."""
    data = {
        "VIN1": {
            "basicVehicleStatus": {"usageMode": "4"}
        }
    }

    class MockCoordinator:
        def __init__(self, data):
            self.data = data

    coordinator = MockCoordinator(data)
    sensor = ZeekrVehicleStatusSensor(coordinator, "VIN1")
    assert sensor.native_value == "Ready to Go"


def test_vehicle_status_sensor_unknown_value():
    """Test ZeekrVehicleStatusSensor returns raw value for unknown status."""
    data = {
        "VIN1": {
            "basicVehicleStatus": {"usageMode": "99"}
        }
    }

    class MockCoordinator:
        def __init__(self, data):
            self.data = data

    coordinator = MockCoordinator(data)
    sensor = ZeekrVehicleStatusSensor(coordinator, "VIN1")
    assert sensor.native_value == "99"


def test_vehicle_status_sensor_no_data():
    """Test ZeekrVehicleStatusSensor returns None when no data."""
    class MockCoordinator:
        def __init__(self, data):
            self.data = data

    coordinator = MockCoordinator({})
    sensor = ZeekrVehicleStatusSensor(coordinator, "VIN1")
    assert sensor.native_value is None


def test_engine_status_sensor():
    """Test ZeekrEngineStatusSensor maps engineStatus correctly."""
    data = {
        "VIN1": {
            "basicVehicleStatus": {"engineStatus": "engine-running"}
        }
    }

    class MockCoordinator:
        def __init__(self, data):
            self.data = data

    coordinator = MockCoordinator(data)
    sensor = ZeekrEngineStatusSensor(coordinator, "VIN1")
    assert sensor.native_value == "Driving"


def test_engine_status_sensor_unknown_value():
    """Test ZeekrEngineStatusSensor returns raw value for unknown status."""
    data = {
        "VIN1": {
            "basicVehicleStatus": {"engineStatus": "unknown-status"}
        }
    }

    class MockCoordinator:
        def __init__(self, data):
            self.data = data

    coordinator = MockCoordinator(data)
    sensor = ZeekrEngineStatusSensor(coordinator, "VIN1")
    assert sensor.native_value == "unknown-status"


def test_charging_time_formatted_sensor():
    """Test ZeekrChargingTimeFormattedSensor formats time correctly."""
    data = {
        "VIN1": {
            "additionalVehicleStatus": {
                "electricVehicleStatus": {"timeToFullyCharged": 173}
            }
        }
    }

    class MockCoordinator:
        def __init__(self, data):
            self.data = data

    coordinator = MockCoordinator(data)
    sensor = ZeekrChargingTimeFormattedSensor(coordinator, "VIN1")
    # 173 minutes = 2h 53m
    assert sensor.native_value == "2h 53m"


def test_charging_time_formatted_sensor_under_hour():
    """Test ZeekrChargingTimeFormattedSensor formats under 1 hour correctly."""
    data = {
        "VIN1": {
            "additionalVehicleStatus": {
                "electricVehicleStatus": {"timeToFullyCharged": 45}
            }
        }
    }

    class MockCoordinator:
        def __init__(self, data):
            self.data = data

    coordinator = MockCoordinator(data)
    sensor = ZeekrChargingTimeFormattedSensor(coordinator, "VIN1")
    assert sensor.native_value == "45m"


def test_charging_time_formatted_sensor_not_charging():
    """Test ZeekrChargingTimeFormattedSensor returns 'Not charging' for 2047."""
    data = {
        "VIN1": {
            "additionalVehicleStatus": {
                "electricVehicleStatus": {"timeToFullyCharged": 2047}
            }
        }
    }

    class MockCoordinator:
        def __init__(self, data):
            self.data = data

    coordinator = MockCoordinator(data)
    sensor = ZeekrChargingTimeFormattedSensor(coordinator, "VIN1")
    assert sensor.native_value == "Not charging"


def test_charging_time_formatted_sensor_no_data():
    """Test ZeekrChargingTimeFormattedSensor returns None when no data."""
    class MockCoordinator:
        def __init__(self, data):
            self.data = data

    coordinator = MockCoordinator({})
    sensor = ZeekrChargingTimeFormattedSensor(coordinator, "VIN1")
    assert sensor.native_value is None


def test_api_status_sensor_connected():
    """Test ZeekrAPIStatusSensor returns Connected when logged in."""
    class MockClient:
        def __init__(self):
            self.logged_in = True
            self.auth_token = "test_auth"
            self.bearer_token = "test_bearer"
            self.username = "test@example.com"
            self.region_code = "EU"
            self.app_server_host = "api.zeekr.com"
            self.usercenter_host = "user.zeekr.com"

    class MockCoordinator:
        def __init__(self):
            self.client = MockClient()
            self.vehicles = []

    coordinator = MockCoordinator()
    sensor = ZeekrAPIStatusSensor(coordinator, "entry_1")
    assert sensor.native_value == "Connected"


def test_api_status_attributes_do_not_expose_credentials_or_vehicle_ids(monkeypatch):
    """API status attributes expose operational metadata only."""
    import custom_components.zeekr_ev.sensor as sensor_module

    username = "privacy-test-user@example.invalid"
    raw_vin = "FAKEVIN-PRIVACY-123"
    encrypted_vin = "fake-encrypted-vin-private"
    auth_token = "fake-auth-token-private"
    bearer_token = "fake-bearer-token-private"
    vin_key = "fake-vin-key-private"
    vin_iv = "fake-vin-iv-private"
    fake_sig = MagicMock()
    fake_sig.aes_encrypt.return_value = encrypted_vin
    monkeypatch.setattr(sensor_module, "zeekr_app_sig_module", fake_sig, raising=False)

    client = MagicMock(
        logged_in=True,
        username=username,
        auth_token=auth_token,
        bearer_token=bearer_token,
        region_code="EU",
        app_server_host="api.example.invalid",
        usercenter_host="user.example.invalid",
        vin_key=vin_key,
        vin_iv=vin_iv,
    )
    coordinator = MagicMock(client=client, vehicles=[MagicMock(vin=raw_vin)])

    attrs = ZeekrAPIStatusSensor(coordinator, "entry_1").extra_state_attributes

    assert set(attrs) == {
        "logged_in",
        "region_code",
        "app_server_host",
        "usercenter_host",
        "vehicle_count",
    }
    serialized = json.dumps(attrs, sort_keys=True)
    for sensitive_value in (
        username,
        raw_vin,
        encrypted_vin,
        auth_token,
        bearer_token,
        vin_key,
        vin_iv,
    ):
        assert sensitive_value not in serialized


def test_api_status_sensor_disconnected():
    """Test ZeekrAPIStatusSensor returns Disconnected when not logged in."""
    class MockCoordinator:
        def __init__(self):
            self.client = None
            self.vehicles = []

    coordinator = MockCoordinator()
    sensor = ZeekrAPIStatusSensor(coordinator, "entry_1")
    assert sensor.native_value == "Disconnected"


# --- Journey Log helpers -------------------------------------------------

def _journey_data(trips, total=50):
    return {"journeyLog": {"total": total, "data": trips}}


# Deliberately out of order (older trip first) — index 0 would be the wrong
# trip here, which is exactly what the startTime lookup guards against.
_JOURNEY_TRIPS = [
    {
        "tripId": 11,
        "startTime": 1781695402000,
        "endTime": 1781695928000,
        "traveledDistance": 7,
    },
    {
        "tripId": 12,
        "startTime": 1781696400000,
        "endTime": 1781696775000,
        "traveledDistance": 4,
    },
]


def test_latest_journey_trip_picks_newest_by_starttime():
    """The newest trip wins on startTime, not on list position."""
    latest = _latest_journey_trip(_journey_data(_JOURNEY_TRIPS))
    assert latest["tripId"] == 12
    assert latest["traveledDistance"] == 4


def test_latest_journey_trip_handles_empty_inputs():
    assert _latest_journey_trip({}) == {}
    assert _latest_journey_trip(_journey_data([])) == {}


def test_journey_last_duration_from_newest_trip():
    # (1781696775000 - 1781696400000) / 60000 = 6.25 -> 6 minutes
    assert _journey_last_duration(_journey_data(_JOURNEY_TRIPS)) == 6


def test_journey_last_duration_missing_times_returns_none():
    assert _journey_last_duration(_journey_data([{"startTime": 1}])) is None
    assert _journey_last_duration({}) is None


# --- Journey Log attribute size cap --------------------------------------

def _make_trips(n):
    """n realistic full trips (with start/end GPS markers + odometers)."""
    base = 1781600000000
    trips = []
    for i in range(n):
        start = base + i * 3_600_000
        trips.append({
            "tripId": 1000 + i,
            "reportTime": start,
            "startTime": start,
            "endTime": start + 1_800_000,
            "traveledDistance": 42.7,
            "avgSpeed": 53.2,
            "electricConsumption": 18.4,
            "electricRegeneration": 560,
            "startOdometer": 12345.6 + i,
            "endOdometer": 12388.3 + i,
            "trackPoints": [
                {"latitude": 52.0907374, "longitude": 5.1214201},
                {"latitude": 52.3675734, "longitude": 4.9041389},
            ],
        })
    return trips


def test_journey_log_attributes_stay_under_ha_16kb_cap():
    """A full 50-trip page must not exceed HA's 16384-byte attribute limit."""
    coordinator = DummyCoordinator({"VIN1": _journey_data(_make_trips(50), total=50)})
    sensor = ZeekrJourneyLogSensor(coordinator, "VIN1")
    attrs = sensor.extra_state_attributes

    assert len(json.dumps(attrs, default=str)) <= 16384
    # The page is capped, but the full count is still reported.
    assert attrs["total_trips"] == 50
    assert attrs["displayed_trips"] == len(attrs["trips"])
    assert attrs["displayed_trips"] < 50
    # Newest trip is kept (sorted newest-first by start_time).
    assert attrs["trips"][0]["trip_id"] == 1049
    # Redundant per-trip vin is dropped; GPS markers are retained.
    assert "vin" not in attrs["trips"][0]
    assert attrs["trips"][0]["start_lat"] == 52.0907374


def test_journey_log_attributes_small_page_keeps_all_trips():
    """A handful of trips fits comfortably and is not capped."""
    coordinator = DummyCoordinator({"VIN1": _journey_data(_make_trips(3), total=3)})
    sensor = ZeekrJourneyLogSensor(coordinator, "VIN1")
    attrs = sensor.extra_state_attributes

    assert attrs["displayed_trips"] == 3
    assert len(json.dumps(attrs, default=str)) <= 16384


def test_journey_log_attributes_empty_when_no_trips():
    coordinator = DummyCoordinator({"VIN1": _journey_data([], total=0)})
    sensor = ZeekrJourneyLogSensor(coordinator, "VIN1")
    assert sensor.extra_state_attributes == {}


def test_journey_log_native_value_zero_when_data_key_missing():
    coordinator = DummyCoordinator({"VIN1": _journey_data([], total=0)})
    sensor = ZeekrJourneyLogSensor(coordinator, "VIN1")
    assert sensor.native_value == 0


def test_journey_log_native_value_zero_when_data_is_null():
    """Regression test: API can return {"data": null} instead of {"data": []}
    (observed on accounts/vehicles with zero recorded trips). native_value
    must not raise TypeError('object of type NoneType has no len()')."""
    coordinator = DummyCoordinator({"VIN1": {"journeyLog": {"total": 0, "data": None}}})
    sensor = ZeekrJourneyLogSensor(coordinator, "VIN1")
    assert sensor.native_value == 0

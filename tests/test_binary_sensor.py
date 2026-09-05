from unittest.mock import MagicMock

import pytest

from custom_components.zeekr_ev.binary_sensor import (
    ZeekrBinarySensor,
    _is_charging,
    _is_plugged_in,
    async_setup_entry,
)
from custom_components.zeekr_ev.const import DOMAIN


class DummyCoordinator:
    def __init__(self, data):
        self.data = data


@pytest.mark.asyncio
async def test_setup_adds_electric_parking_brake_as_read_only_binary_sensor():
    coordinator = DummyCoordinator(
        {
            "VIN1": {
                "additionalVehicleStatus": {
                    "drivingSafetyStatus": {"electricParkBrakeStatus": "1"}
                }
            }
        }
    )
    entry = MagicMock()
    entry.entry_id = "entry-1"
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator}}
    add_entities = MagicMock()

    await async_setup_entry(hass, entry, add_entities)

    entities = {entity.key: entity for entity in add_entities.call_args.args[0]}
    assert entities["electric_parking_brake_applied"].is_on is True


def test_is_on_none_when_no_data():
    coordinator = DummyCoordinator({})
    bs = ZeekrBinarySensor(coordinator, "VIN1", "charging_status", "Charging Status", lambda d: True)
    assert bs.is_on is None


def test_charging_status_true_false():
    data_true = {
        "VIN1": {"additionalVehicleStatus": {"electricVehicleStatus": {"isCharging": True}}}
    }
    coordinator = DummyCoordinator(data_true)
    bs = ZeekrBinarySensor(coordinator, "VIN1", "charging_status", "Charging Status", lambda d: d.get("additionalVehicleStatus", {}).get("electricVehicleStatus", {}).get("isCharging"))
    assert bs.is_on is True

    data_false = {
        "VIN1": {"additionalVehicleStatus": {"electricVehicleStatus": {"isCharging": False}}}
    }
    coordinator = DummyCoordinator(data_false)
    bs = ZeekrBinarySensor(coordinator, "VIN1", "charging_status", "Charging Status", lambda d: d.get("additionalVehicleStatus", {}).get("electricVehicleStatus", {}).get("isCharging"))
    assert bs.is_on is False


def test_plugged_in_prefers_explicit_boolean_over_connection_enum():
    """The direct API boolean wins when merged endpoint fields disagree."""
    data = {
        "additionalVehicleStatus": {
            "electricVehicleStatus": {
                "isPluggedIn": False,
                "statusOfChargerConnection": "2",
            }
        }
    }
    assert _is_plugged_in(data) is False
    data["additionalVehicleStatus"]["electricVehicleStatus"]["isPluggedIn"] = True
    assert _is_plugged_in(data) is True


def test_plugged_in_falls_back_for_legacy_payloads():
    data = {
        "additionalVehicleStatus": {
            "electricVehicleStatus": {"statusOfChargerConnection": "2"}
        }
    }
    assert _is_plugged_in(data) is True
    assert _is_plugged_in({}) is None


def test_charging_prefers_explicit_boolean_and_falls_back_to_enum():
    ev = {"isCharging": False, "chargerState": "2"}
    data = {"additionalVehicleStatus": {"electricVehicleStatus": ev}}
    assert _is_charging(data) is False
    ev.pop("isCharging")
    assert _is_charging(data) is True
    ev["chargerState"] = "26"
    assert _is_charging(data) is False
    assert _is_charging({}) is None


@pytest.mark.parametrize("malformed", ["unknown", object(), 2])
def test_malformed_explicit_boole_use_legacy_fallback(malformed):
    status = {
        "isPluggedIn": malformed,
        "statusOfChargerConnection": "0",
        "isCharging": malformed,
        "chargerState": "26",
    }
    data = {"additionalVehicleStatus": {"electricVehicleStatus": status}}

    assert _is_plugged_in(data) is False
    assert _is_charging(data) is False


def test_tire_warning_sensors():
    # Test NO warning
    data_ok = {
        "VIN1": {
            "additionalVehicleStatus": {
                "maintenanceStatus": {
                    "tyrePreWarningDriver": 0,
                    "tyrePreWarningPassenger": 0,
                    "tyrePreWarningDriverRear": 0,
                    "tyrePreWarningPassengerRear": 0,
                    "tyreTempWarningDriver": 0,
                    "tyreTempWarningPassenger": 0,
                    "tyreTempWarningDriverRear": 0,
                    "tyreTempWarningPassengerRear": 0,
                }
            }
        }
    }
    coordinator = DummyCoordinator(data_ok)

    # Pre-Warning
    for tire in ["Driver", "Passenger", "DriverRear", "PassengerRear"]:
        bs = ZeekrBinarySensor(
            coordinator,
            "VIN1",
            f"tire_pre_warning_{tire.lower()}",
            f"Tire Pre-Warning {tire}",
            lambda d, t=tire: (
                None if (v := d.get("additionalVehicleStatus", {}).get("maintenanceStatus", {}).get(f"tyrePreWarning{t}")) is None else str(v) != "0"
            ),
        )
        assert bs.is_on is False

    # Temp Warning
    for tire in ["Driver", "Passenger", "DriverRear", "PassengerRear"]:
        bs = ZeekrBinarySensor(
            coordinator,
            "VIN1",
            f"tire_temp_warning_{tire.lower()}",
            f"Tire Temp Warning {tire}",
            lambda d, t=tire: (
                None if (v := d.get("additionalVehicleStatus", {}).get("maintenanceStatus", {}).get(f"tyreTempWarning{t}")) is None else str(v) != "0"
            ),
        )
        assert bs.is_on is False

    # Test WITH warning (e.g. value "1")
    data_warn = {
        "VIN1": {
            "additionalVehicleStatus": {
                "maintenanceStatus": {
                    "tyrePreWarningDriver": 1,
                    "tyreTempWarningDriver": 1,
                }
            }
        }
    }
    coordinator = DummyCoordinator(data_warn)

    # Check Driver warning active
    bs_pre = ZeekrBinarySensor(
        coordinator,
        "VIN1",
        "tire_pre_warning_driver",
        "Tire Pre-Warning Driver",
        lambda d: (None if (v := d.get("additionalVehicleStatus", {}).get("maintenanceStatus", {}).get("tyrePreWarningDriver")) is None else str(v) != "0"),
    )
    assert bs_pre.is_on is True

    bs_temp = ZeekrBinarySensor(
        coordinator,
        "VIN1",
        "tire_temp_warning_driver",
        "Tire Temp Warning Driver",
        lambda d: (None if (v := d.get("additionalVehicleStatus", {}).get("maintenanceStatus", {}).get("tyreTempWarningDriver")) is None else str(v) != "0"),
    )
    assert bs_temp.is_on is True

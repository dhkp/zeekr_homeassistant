"""Binary sensor platform for Zeekr EV API Integration."""

from __future__ import annotations

from numbers import Number

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_DRIVE_SIDE, DRIVE_SIDE_LHD
from .coordinator import ZeekrCoordinator


def _explicit_bool(value) -> bool | None:
    """Normalize a boolean API value, rejecting ambiguous values."""
    if isinstance(value, bool):
        return value
    if isinstance(value, Number):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
    return None


def _electric_vehicle_status(data: dict) -> dict:
    """Return the electric-vehicle status subtree."""
    return data.get("additionalVehicleStatus", {}).get("electricVehicleStatus", {})


def _is_plugged_in(data: dict) -> bool | None:
    """Reconcile plug state across API fields, preferring any positive signal."""
    status = _electric_vehicle_status(data)
    explicit = _explicit_bool(status.get("isPluggedIn"))
    connection = status.get("statusOfChargerConnection")
    fallback = None
    if connection is not None:
        try:
            fallback = int(connection) != 0
        except (TypeError, ValueError):
            pass
    if explicit is True or fallback is True:
        return True
    if explicit is False or fallback is False:
        return False
    return None


def _is_charging(data: dict) -> bool | None:
    """Reconcile charging state across API fields, preferring positive signals."""
    status = _electric_vehicle_status(data)
    explicit = _explicit_bool(status.get("isCharging"))
    charger_state = status.get("chargerState")
    fallback = None
    if charger_state is not None:
        try:
            fallback = int(charger_state) in {1, 2, 15}
        except (TypeError, ValueError):
            pass
    if explicit is True or fallback is True:
        return True
    if explicit is False or fallback is False:
        return False
    return None


class ZeekrBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Zeekr Binary Sensor class."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ZeekrCoordinator,
        vin: str,
        key: str,
        name: str,
        value_fn,
        device_class: BinarySensorDeviceClass | None = None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.vin = vin
        self.key = key
        self._attr_name = name
        self._attr_unique_id = f"{vin}_{key}"
        self._value_fn = value_fn
        self._attr_device_class = device_class

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        data = self.coordinator.data.get(self.vin, {})
        if not data:
            return None
        return self._value_fn(data)

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self.vin)},
            "name": f"Zeekr {self.vin}",
            "manufacturer": "Zeekr",
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator: ZeekrCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for vin in coordinator.data:
        # Charging Status
        entities.append(
            ZeekrBinarySensor(
                coordinator,
                vin,
                "charging_status",
                "Charging Status",
                _is_charging,
                BinarySensorDeviceClass.BATTERY_CHARGING,
            )
        )
        # Plugged In Status
        entities.append(
            ZeekrBinarySensor(
                coordinator,
                vin,
                "plugged_in",
                "Plugged In",
                _is_plugged_in,
                BinarySensorDeviceClass.PLUG,
            )
        )

        # Door open sensors from drivingSafetyStatus
        door_fields = {
            "door_open_driver": ("doorOpenStatusDriver", "Driver door open"),
            "door_open_passenger": ("doorOpenStatusPassenger", "Passenger door open"),
            "door_open_driver_rear": (
                "doorOpenStatusDriverRear",
                "Driver rear door open",
            ),
            "door_open_passenger_rear": (
                "doorOpenStatusPassengerRear",
                "Passenger rear door open",
            ),
            "trunk_open": ("trunkOpenStatus", "Trunk open"),
            "hood_open": ("engineHoodOpenStatus", "Hood open"),
        }

        for key, (field_name, label) in door_fields.items():
            entities.append(
                ZeekrBinarySensor(
                    coordinator,
                    vin,
                    key,
                    label,
                    lambda d, f=field_name: (
                        None
                        if (
                            v := d.get("additionalVehicleStatus", {})
                            .get("drivingSafetyStatus", {})
                            .get(f)
                        )
                        is None
                        else str(v) == "1"
                    ),
                    BinarySensorDeviceClass.DOOR,
                )
            )

        entities.append(
            ZeekrBinarySensor(
                coordinator,
                vin,
                "electric_parking_brake_applied",
                "Electric Parking Brake Applied",
                lambda d: (
                    None
                    if (
                        value := d.get("additionalVehicleStatus", {})
                        .get("drivingSafetyStatus", {})
                        .get("electricParkBrakeStatus")
                    )
                    is None
                    else str(value) == "1"
                ),
            )
        )

        # Tire Pre-Warning & Temp Warning
        from .sensor import get_tire_position_label
        drive_side = entry.data.get(CONF_DRIVE_SIDE, DRIVE_SIDE_LHD)
        for tire in ["Driver", "Passenger", "DriverRear", "PassengerRear"]:
            display_label = get_tire_position_label(tire, drive_side)
            # Pre-Warning
            entities.append(
                ZeekrBinarySensor(
                    coordinator,
                    vin,
                    f"tire_pre_warning_{tire.lower()}",
                    f"Tire Pre-Warning {display_label}",
                    lambda d, t=tire: (
                        None
                        if (
                            v := d.get("additionalVehicleStatus", {})
                            .get("maintenanceStatus", {})
                            .get(f"tyrePreWarning{t}")
                        )
                        is None
                        else str(v) != "0"
                    ),
                    BinarySensorDeviceClass.PROBLEM,
                )
            )
            # Temp Warning
            entities.append(
                ZeekrBinarySensor(
                    coordinator,
                    vin,
                    f"tire_temp_warning_{tire.lower()}",
                    f"Tire Temp Warning {display_label}",
                    lambda d, t=tire: (
                        None
                        if (
                            v := d.get("additionalVehicleStatus", {})
                            .get("maintenanceStatus", {})
                            .get(f"tyreTempWarning{t}")
                        )
                        is None
                        else str(v) != "0"
                    ),
                    BinarySensorDeviceClass.PROBLEM,
                )
            )

    async_add_entities(entities)

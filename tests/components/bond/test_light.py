"""Tests for the Bond light device."""
from datetime import timedelta

from bond_api import Action, DeviceType

from homeassistant import core
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    DOMAIN as LIGHT_DOMAIN,
    SUPPORT_BRIGHTNESS,
)
from homeassistant.const import (
    ATTR_ASSUMED_STATE,
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.util import utcnow

from .common import (
    help_test_entity_available,
    patch_bond_action,
    patch_bond_device_state,
    setup_platform,
)

from tests.common import async_fire_time_changed


def ceiling_fan(name: str):
    """Create a ceiling fan (that has built-in light) with given name."""
    return {
        "name": name,
        "type": DeviceType.CEILING_FAN,
        "actions": [Action.TURN_LIGHT_ON, Action.TURN_LIGHT_OFF],
    }


def dimmable_ceiling_fan(name: str):
    """Create a ceiling fan (that has built-in light) with given name."""
    return {
        "name": name,
        "type": DeviceType.CEILING_FAN,
        "actions": [Action.TURN_LIGHT_ON, Action.TURN_LIGHT_OFF, Action.SET_BRIGHTNESS],
    }


def fireplace(name: str):
    """Create a fireplace with given name."""
    return {"name": name, "type": DeviceType.FIREPLACE}


async def test_entity_registry(hass: core.HomeAssistant):
    """Tests that the devices are registered in the entity registry."""
    await setup_platform(
        hass,
        LIGHT_DOMAIN,
        ceiling_fan("name-1"),
        bond_version={"bondid": "test-hub-id"},
        bond_device_id="test-device-id",
    )

    registry: EntityRegistry = await hass.helpers.entity_registry.async_get_registry()
    entity = registry.entities["light.name_1"]
    assert entity.unique_id == "test-hub-id_test-device-id"


async def test_sbb_trust_state(hass: core.HomeAssistant):
    """Assumed state should be False if device is a Smart by Bond."""
    version = {
        "model": "MR123A",
        "bondid": "test-bond-id",
    }
    await setup_platform(
        hass, LIGHT_DOMAIN, ceiling_fan("name-1"), bond_version=version
    )

    device = hass.states.get("light.name_1")
    assert device.attributes.get(ATTR_ASSUMED_STATE) is not True


async def test_trust_state_not_specified(hass: core.HomeAssistant):
    """Assumed state should be True if Trust State is not specified."""
    await setup_platform(hass, LIGHT_DOMAIN, ceiling_fan("name-1"))

    device = hass.states.get("light.name_1")
    assert device.attributes.get(ATTR_ASSUMED_STATE) is True


async def test_trust_state(hass: core.HomeAssistant):
    """Assumed state should be True if Trust State is False."""
    await setup_platform(
        hass, LIGHT_DOMAIN, ceiling_fan("name-1"), props={"trust_state": False}
    )

    device = hass.states.get("light.name_1")
    assert device.attributes.get(ATTR_ASSUMED_STATE) is True


async def test_no_trust_state(hass: core.HomeAssistant):
    """Assumed state should be False if Trust State is True."""
    await setup_platform(
        hass, LIGHT_DOMAIN, ceiling_fan("name-1"), props={"trust_state": True}
    )
    device = hass.states.get("light.name_1")
    assert device.attributes.get(ATTR_ASSUMED_STATE) is not True


async def test_turn_on_light(hass: core.HomeAssistant):
    """Tests that turn on command delegates to API."""
    await setup_platform(
        hass, LIGHT_DOMAIN, ceiling_fan("name-1"), bond_device_id="test-device-id"
    )

    with patch_bond_action() as mock_turn_light_on, patch_bond_device_state():
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "light.name_1"},
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_turn_light_on.assert_called_once_with("test-device-id", Action.turn_light_on())


async def test_turn_off_light(hass: core.HomeAssistant):
    """Tests that turn off command delegates to API."""
    await setup_platform(
        hass, LIGHT_DOMAIN, ceiling_fan("name-1"), bond_device_id="test-device-id"
    )

    with patch_bond_action() as mock_turn_light_off, patch_bond_device_state():
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "light.name_1"},
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_turn_light_off.assert_called_once_with(
        "test-device-id", Action.turn_light_off()
    )


async def test_brightness_support(hass: core.HomeAssistant):
    """Tests that a dimmable light should support the brightness feature."""
    await setup_platform(
        hass,
        LIGHT_DOMAIN,
        dimmable_ceiling_fan("name-1"),
        bond_device_id="test-device-id",
    )

    state = hass.states.get("light.name_1")
    assert state.attributes[ATTR_SUPPORTED_FEATURES] & SUPPORT_BRIGHTNESS


async def test_brightness_not_supported(hass: core.HomeAssistant):
    """Tests that a non-dimmable light should not support the brightness feature."""
    await setup_platform(
        hass,
        LIGHT_DOMAIN,
        ceiling_fan("name-1"),
        bond_device_id="test-device-id",
    )

    state = hass.states.get("light.name_1")
    assert not state.attributes[ATTR_SUPPORTED_FEATURES] & SUPPORT_BRIGHTNESS


async def test_turn_on_light_with_brightness(hass: core.HomeAssistant):
    """Tests that turn on command, on a dimmable light, delegates to API and parses brightness."""
    await setup_platform(
        hass,
        LIGHT_DOMAIN,
        dimmable_ceiling_fan("name-1"),
        bond_device_id="test-device-id",
    )

    with patch_bond_action() as mock_set_brightness, patch_bond_device_state():
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "light.name_1", ATTR_BRIGHTNESS: 128},
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_set_brightness.assert_called_once_with(
        "test-device-id", Action(Action.SET_BRIGHTNESS, 50)
    )


async def test_update_reports_light_is_on(hass: core.HomeAssistant):
    """Tests that update command sets correct state when Bond API reports the light is on."""
    await setup_platform(hass, LIGHT_DOMAIN, ceiling_fan("name-1"))

    with patch_bond_device_state(return_value={"light": 1}):
        async_fire_time_changed(hass, utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done()

    assert hass.states.get("light.name_1").state == "on"


async def test_update_reports_light_is_off(hass: core.HomeAssistant):
    """Tests that update command sets correct state when Bond API reports the light is off."""
    await setup_platform(hass, LIGHT_DOMAIN, ceiling_fan("name-1"))

    with patch_bond_device_state(return_value={"light": 0}):
        async_fire_time_changed(hass, utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done()

    assert hass.states.get("light.name_1").state == "off"


async def test_turn_on_fireplace_with_brightness(hass: core.HomeAssistant):
    """Tests that turn on command delegates to set flame API."""
    await setup_platform(
        hass, LIGHT_DOMAIN, fireplace("name-1"), bond_device_id="test-device-id"
    )

    with patch_bond_action() as mock_set_flame, patch_bond_device_state():
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "light.name_1", ATTR_BRIGHTNESS: 128},
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_set_flame.assert_called_once_with("test-device-id", Action.set_flame(50))


async def test_turn_on_fireplace_without_brightness(hass: core.HomeAssistant):
    """Tests that turn on command delegates to turn on API."""
    await setup_platform(
        hass, LIGHT_DOMAIN, fireplace("name-1"), bond_device_id="test-device-id"
    )

    with patch_bond_action() as mock_turn_on, patch_bond_device_state():
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "light.name_1"},
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_turn_on.assert_called_once_with("test-device-id", Action.turn_on())


async def test_turn_off_fireplace(hass: core.HomeAssistant):
    """Tests that turn off command delegates to API."""
    await setup_platform(
        hass, LIGHT_DOMAIN, fireplace("name-1"), bond_device_id="test-device-id"
    )

    with patch_bond_action() as mock_turn_off, patch_bond_device_state():
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "light.name_1"},
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_turn_off.assert_called_once_with("test-device-id", Action.turn_off())


async def test_flame_converted_to_brightness(hass: core.HomeAssistant):
    """Tests that reported flame level (0..100) converted to HA brightness (0...255)."""
    await setup_platform(hass, LIGHT_DOMAIN, fireplace("name-1"))

    with patch_bond_device_state(return_value={"power": 1, "flame": 50}):
        async_fire_time_changed(hass, utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done()

    assert hass.states.get("light.name_1").attributes[ATTR_BRIGHTNESS] == 128


async def test_light_available(hass: core.HomeAssistant):
    """Tests that available state is updated based on API errors."""
    await help_test_entity_available(
        hass, LIGHT_DOMAIN, ceiling_fan("name-1"), "light.name_1"
    )


async def test_parse_brightness(hass: core.HomeAssistant):
    """Tests that reported brightness level (0..100) converted to HA brightness (0...255)."""
    await setup_platform(hass, LIGHT_DOMAIN, dimmable_ceiling_fan("name-1"))

    with patch_bond_device_state(return_value={"light": 1, "brightness": 50}):
        async_fire_time_changed(hass, utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done()

    assert hass.states.get("light.name_1").attributes[ATTR_BRIGHTNESS] == 128

"""Support for Overkiz select devices."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ENTITY_CATEGORY_CONFIG
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import OverkizDescriptiveEntity, OverkizSelectDescription

SELECT_DESCRIPTIONS = [
    OverkizSelectDescription(
        key="core:OpenClosedPedestrianState",
        name="Position",
        icon="mdi:content-save-cog",
        options=["closed", "open", "pedestrian"],
        select_option=lambda option, execute_command: execute_command(
            {
                "closed": "close",
                "open": "open",
                "pedestrian": "setPedestrianPosition",
            }[option]
        ),
    ),
    OverkizSelectDescription(
        key="io:MemorizedSimpleVolumeState",
        name="Memorized Simple Volume",
        icon="mdi:volume-high",
        options=["highest", "standard"],
        select_option=lambda option, execute_command: execute_command(
            "setMemorizedSimpleVolume", option
        ),
        entity_category=ENTITY_CATEGORY_CONFIG,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up the Overkiz select from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    entities = []

    key_supported_states = {
        description.key: description for description in SELECT_DESCRIPTIONS
    }

    for device in coordinator.data.values():
        for state in device.definition.states:
            if description := key_supported_states.get(state.qualified_name):
                entities.append(
                    OverkizSelect(
                        device.device_url,
                        coordinator,
                        description,
                    )
                )

    async_add_entities(entities)


class OverkizSelect(OverkizDescriptiveEntity, SelectEntity):
    """Representation of an Overkiz Number entity."""

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        if state := self.device.states.get(self.entity_description.key):
            return state.value

        return None

    @property
    def options(self):
        """Return a set of selectable options."""
        return self.entity_description.options

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.entity_description.select_option(
            option, self.executor.async_execute_command
        )

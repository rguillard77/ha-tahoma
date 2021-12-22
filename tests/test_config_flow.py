from unittest.mock import Mock, patch

from aiohttp import ClientError
from homeassistant import config_entries, data_entry_flow, setup
from homeassistant.components import dhcp
from pyoverkiz.exceptions import (
    BadCredentialsException,
    MaintenanceException,
    TooManyRequestsException,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_device_registry,
)

from custom_components.tahoma import config_flow

TEST_EMAIL = "test@testdomain.com"
TEST_EMAIL2 = "test@testdomain.nl"
TEST_PASSWORD = "test-password"
TEST_PASSWORD2 = "test-password2"
TEST_HUB = "somfy_europe"
TEST_HUB2 = "hi_kumo_europe"
TEST_GATEWAY_ID = "1234-5678-9123"
TEST_GATEWAY_ID2 = "4321-5678-9123"

MOCK_GATEWAY_RESPONSE = [Mock(id=TEST_GATEWAY_ID)]


async def test_form(hass):
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == "form"
    assert result["errors"] == {}

    with patch("pyoverkiz.client.OverkizClient.login", return_value=True), patch(
        "pyoverkiz.client.OverkizClient.get_gateways", return_value=None
    ), patch(
        "custom_components.tahoma.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": TEST_EMAIL, "password": TEST_PASSWORD, "hub": TEST_HUB},
        )

    assert result2["type"] == "create_entry"
    assert result2["title"] == TEST_EMAIL
    assert result2["data"] == {
        "username": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "hub": TEST_HUB,
    }

    await hass.async_block_till_done()

    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    "side_effect, error",
    [
        (BadCredentialsException, "invalid_auth"),
        (TooManyRequestsException, "too_many_requests"),
        (TimeoutError, "cannot_connect"),
        (ClientError, "cannot_connect"),
        (MaintenanceException, "server_in_maintenance"),
        (Exception, "unknown"),
    ],
)
async def test_form_invalid(hass, side_effect, error):
    """Test we handle invalid auth."""
    result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch("pyoverkiz.client.OverkizClient.login", side_effect=side_effect):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": TEST_EMAIL, "password": TEST_PASSWORD, "hub": TEST_HUB},
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": error}


async def test_abort_on_duplicate_entry(hass):
    """Test config flow aborts Config Flow on duplicate entries."""
    MockConfigEntry(
        domain=config_flow.DOMAIN,
        unique_id=TEST_GATEWAY_ID,
        data={"username": TEST_EMAIL, "password": TEST_PASSWORD, "hub": TEST_HUB},
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch("pyoverkiz.client.OverkizClient.login", return_value=True), patch(
        "pyoverkiz.client.OverkizClient.get_gateways",
        return_value=MOCK_GATEWAY_RESPONSE,
    ), patch("custom_components.tahoma.async_setup_entry", return_value=True):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": TEST_EMAIL, "password": TEST_PASSWORD},
        )

    assert result2["type"] == "abort"
    assert result2["reason"] == "already_configured"


async def test_allow_multiple_unique_entries(hass):
    """Test config flow allows Config Flow unique entries."""
    MockConfigEntry(
        domain=config_flow.DOMAIN,
        unique_id="test2@testdomain.com",
        data={"username": "test2@testdomain.com", "password": TEST_PASSWORD},
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch("pyoverkiz.client.OverkizClient.login", return_value=True), patch(
        "pyoverkiz.client.OverkizClient.get_gateways",
        return_value=MOCK_GATEWAY_RESPONSE,
    ), patch("custom_components.tahoma.async_setup_entry", return_value=True):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": TEST_EMAIL, "password": TEST_PASSWORD, "hub": TEST_HUB},
        )

    assert result2["type"] == "create_entry"
    assert result2["title"] == TEST_EMAIL
    assert result2["data"] == {
        "username": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "hub": TEST_HUB,
    }


async def test_reauth_success(hass):
    """Test reauthentication flow."""
    await setup.async_setup_component(hass, "persistent_notification", {})

    with patch(
        "pyoverkiz.client.OverkizClient.login", side_effect=BadCredentialsException
    ):
        mock_entry = MockConfigEntry(
            domain=config_flow.DOMAIN,
            unique_id=TEST_GATEWAY_ID,
            data={"username": TEST_EMAIL, "password": TEST_PASSWORD, "hub": TEST_HUB2},
        )
        mock_entry.add_to_hass(hass)

        result = await hass.config_entries.flow.async_init(
            config_flow.DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "unique_id": mock_entry.unique_id,
                "entry_id": mock_entry.entry_id,
            },
            data=mock_entry.data,
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "user"

    with patch("pyoverkiz.client.OverkizClient.login", return_value=True), patch(
        "pyoverkiz.client.OverkizClient.get_gateways",
        return_value=MOCK_GATEWAY_RESPONSE,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                "username": TEST_EMAIL,
                "password": TEST_PASSWORD2,
                "hub": TEST_HUB2,
            },
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
        assert result["reason"] == "reauth_successful"
        assert mock_entry.data["username"] == TEST_EMAIL
        assert mock_entry.data["password"] == TEST_PASSWORD2


async def test_dhcp_flow(hass):
    """Test that DHCP discovery for new bridge works."""
    result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN,
        data=dhcp.DhcpServiceInfo(
            hostname="gateway-1234-5678-9123",
            ip="192.168.1.4",
            macaddress="F8811A000000",
        ),
        context={"source": config_entries.SOURCE_DHCP},
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == config_entries.SOURCE_USER


async def test_dhcp_flow_already_configured(hass):
    """Test that DHCP doesn't setup already configured gateways."""
    config_entry = MockConfigEntry(
        domain=config_flow.DOMAIN,
        unique_id=TEST_EMAIL,
        data={"username": TEST_EMAIL, "password": TEST_PASSWORD, "hub": TEST_HUB},
    )
    config_entry.add_to_hass(hass)

    device_registry = mock_device_registry(hass)
    device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(config_flow.DOMAIN, "1234-5678-9123")},
    )

    result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN,
        data=dhcp.DhcpServiceInfo(
            hostname="gateway-1234-5678-9123",
            ip="192.168.1.4",
            macaddress="F8811A000000",
        ),
        context={"source": config_entries.SOURCE_DHCP},
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == "already_configured"

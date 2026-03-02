from unittest.mock import patch, MagicMock

from app.tools.mandi import get_mandi_prices
from app.cache import cache_set


MOCK_API_RESPONSE = {
    "records": [
        {
            "commodity": "Wheat",
            "market": "Sehore",
            "state": "Madhya Pradesh",
            "modal_price": "2200",
            "min_price": "2000",
            "max_price": "2400",
            "arrival_date": "01/03/2026",
        }
    ]
}


@patch("app.tools.mandi.httpx.get")
def test_get_mandi_prices_returns_price(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_API_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    result = get_mandi_prices("Wheat", "Madhya Pradesh", "Sehore")

    assert "prices" in result
    assert result["prices"][0]["commodity"] == "Wheat"
    assert result["prices"][0]["modal_price"] == "2200"
    mock_get.assert_called_once()


@patch("app.tools.mandi.httpx.get")
def test_mandi_prices_uses_cache(mock_get):
    cache_set("mandi:Wheat:Madhya Pradesh:Sehore", {"commodity": "Wheat", "price": "2200"})

    result = get_mandi_prices("Wheat", "Madhya Pradesh", "Sehore")

    assert result["commodity"] == "Wheat"
    assert result["price"] == "2200"
    mock_get.assert_not_called()

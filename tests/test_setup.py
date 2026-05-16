from travel_agent.setup import build_mcp_server, select_provider


def test_select_provider_returns_some_or_none():
    # conftest scrubs Anthropic/OpenAI; depending on what's in the env, this may return
    # google (if GOOGLE_API_KEY set) or None. Either is valid for the test environment.
    sel = select_provider()
    assert sel is None or sel[0] in {"openai", "anthropic", "google"}


def test_build_mcp_server_registers_all_tools():
    srv = build_mcp_server()
    names = {t["name"] for t in srv.list_tools()}
    expected = {
        "search_flights",
        "book_flight",
        "search_hotels",
        "rent_car",
        "get_forecast",
        "create_payment_session",
        "get_payment_status",
        "get_current_datetime",
    }
    assert expected.issubset(names)

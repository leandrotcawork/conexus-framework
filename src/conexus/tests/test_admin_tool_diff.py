from conexus.web.admin.services.tool_diff import diff_for_connector


def test_diff_counts_tools_and_estimates_tokens() -> None:
    res = diff_for_connector(
        connector_name="gcal",
        new_tool_names=["list_events", "create_event", "update_event"],
        sample_descriptions={"list_events": "List calendar events.",
                             "create_event": "Create a calendar event.",
                             "update_event": "Update an existing event."},
    )
    assert res.added_tools == 3
    assert res.estimated_tokens > 0
    assert res.estimated_cost_per_turn_usd > 0

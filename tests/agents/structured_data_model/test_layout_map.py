from src.agents.structured_data_model.layout_map import LayoutMap, LayoutComponent

def test_layout_map_validation():
    component = {
        "type": "table",
        "description": "Consolidated Balance Sheets",
        "coordinates_hint": "Top of page 45"
    }
    layout = LayoutMap(components=[component], nested_table_count=1)
    assert layout.components[0].type == "table"
    assert layout.nested_table_count == 1

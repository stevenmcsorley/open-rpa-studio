from openrpa.activity_catalog import ACTIVITY_CATALOG


def test_native_activity_catalog_has_unique_stable_activity_types():
    types=[item["type"] for item in ACTIVITY_CATALOG]
    assert len(types)==len(set(types))
    assert types.count("sort_rows")==1
    assert types.count("map_rows")==1
    assert types.count("distinct_rows")==1
    assert types.count("validate_rows")==1
    assert types.count("image_ocr")==1
    by_type={item["type"]:item for item in ACTIVITY_CATALOG}
    assert by_type["desktop_ui_expand"]["defaults"]["controlType"]=="TreeItem"
    assert by_type["desktop_ui_collapse"]["defaults"]["controlType"]=="TreeItem"
    assert by_type["desktop_ui_set_range_value"]["defaults"]["controlType"]=="Slider"

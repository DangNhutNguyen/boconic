import pytest
from app.core.errors import BoconicException, ErrorCode
from app.db.models.custom_fields import CustomFieldDefinition
from app.services.custom_fields import CustomFieldsService

@pytest.mark.asyncio
async def test_custom_fields_validation_and_schema(db_session):
    # 1. Create definitions
    field_curr = CustomFieldDefinition(
        entity_type="book",
        key="curriculum_series",
        label="Bộ sách giáo khoa",
        field_type="single_select",
        required=True,
        options=[
            {"id": "kn_tri_thuc", "label": "Kết nối tri thức"},
            {"id": "canh_dieu", "label": "Cánh Diều"},
        ],
    )
    field_pages = CustomFieldDefinition(
        entity_type="book",
        key="page_count",
        label="Tổng số trang",
        field_type="integer",
        required=False,
        validation_rules={"min_value": 1, "max_value": 2000},
    )
    field_price = CustomFieldDefinition(
        entity_type="book",
        key="cover_price",
        label="Giá bìa",
        field_type="decimal",
        required=False,
    )
    db_session.add_all([field_curr, field_pages, field_price])
    await db_session.flush()

    # 2. Test valid input
    data_valid = {
        "curriculum_series": "kn_tri_thuc",
        "page_count": 250,
        "cover_price": "35000.50",
    }
    cleaned = await CustomFieldsService.validate_custom_data(db_session, "book", data_valid)
    assert cleaned["curriculum_series"] == "kn_tri_thuc"
    assert cleaned["page_count"] == 250
    assert cleaned["cover_price"] == "35000.50"

    # 3. Test invalid single_select option
    with pytest.raises(BoconicException) as exc_opt:
        await CustomFieldsService.validate_custom_data(
            db_session, "book", {"curriculum_series": "invalid_option"}
        )
    assert exc_opt.value.code == ErrorCode.VALIDATION_ERROR

    # 4. Test missing required field
    with pytest.raises(BoconicException) as exc_req:
        await CustomFieldsService.validate_custom_data(
            db_session, "book", {"page_count": 100}
        )
    assert exc_req.value.code == ErrorCode.VALIDATION_ERROR

import datetime
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BoconicException, ErrorCode
from app.db.models.custom_fields import CustomFieldDefinition

SUPPORTED_FIELD_TYPES = {
    "text", "textarea", "integer", "decimal", "boolean", "date", "datetime",
    "single_select", "multi_select", "url", "email", "phone", "image", "file", "json", "reference"
}

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")
PHONE_REGEX = re.compile(r"^\+?[0-9\s\-\(\)]{7,20}$")
URL_REGEX = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)

class CustomFieldsService:
    @staticmethod
    async def get_definitions_for_entity(
        db: AsyncSession, entity_type: str, active_only: bool = True
    ) -> List[CustomFieldDefinition]:
        stmt = select(CustomFieldDefinition).where(CustomFieldDefinition.entity_type == entity_type)
        if active_only:
            stmt = stmt.where(CustomFieldDefinition.active.is_(True))
        stmt = stmt.order_by(CustomFieldDefinition.display_order.asc(), CustomFieldDefinition.key.asc())
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    def validate_field_value(definition: CustomFieldDefinition, value: Any) -> Any:
        """Validate a single custom field value according to its definition. Returns cleaned value."""
        ft = definition.field_type
        key = definition.key

        if value is None or value == "":
            if definition.required:
                raise BoconicException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"Trường tùy chỉnh '{definition.label}' ({key}) là bắt buộc.",
                    details={"field": key},
                )
            return None

        # Type-specific validation
        if ft == "text":
            val_str = str(value).strip()
            max_len = definition.validation_rules.get("max_length", 255)
            if len(val_str) > max_len:
                raise BoconicException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"Trường '{definition.label}' vượt quá {max_len} ký tự.",
                )
            return val_str

        elif ft == "textarea":
            val_str = str(value).strip()
            max_len = definition.validation_rules.get("max_length", 5000)
            if len(val_str) > max_len:
                raise BoconicException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"Trường '{definition.label}' vượt quá {max_len} ký tự.",
                )
            return val_str

        elif ft == "integer":
            try:
                val_int = int(value)
            except (ValueError, TypeError):
                raise BoconicException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"Trường '{definition.label}' phải là số nguyên hợp lệ.",
                )
            min_val = definition.validation_rules.get("min_value")
            max_val = definition.validation_rules.get("max_value")
            if min_val is not None and val_int < min_val:
                raise BoconicException(code=ErrorCode.VALIDATION_ERROR, message=f"'{definition.label}' phải >= {min_val}.")
            if max_val is not None and val_int > max_val:
                raise BoconicException(code=ErrorCode.VALIDATION_ERROR, message=f"'{definition.label}' phải <= {max_val}.")
            return val_int

        elif ft == "decimal":
            try:
                val_dec = Decimal(str(value))
            except InvalidOperation:
                raise BoconicException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"Trường '{definition.label}' phải là số thập phân hợp lệ.",
                )
            return str(val_dec) # preserve exact string representation

        elif ft == "boolean":
            if isinstance(value, bool):
                return value
            if str(value).lower() in ("true", "1", "yes", "on"):
                return True
            if str(value).lower() in ("false", "0", "no", "off"):
                return False
            raise BoconicException(code=ErrorCode.VALIDATION_ERROR, message=f"'{definition.label}' phải là boolean.")

        elif ft == "date":
            val_str = str(value).strip()
            try:
                datetime.date.fromisoformat(val_str)
                return val_str
            except ValueError:
                raise BoconicException(code=ErrorCode.VALIDATION_ERROR, message=f"'{definition.label}' phải có định dạng YYYY-MM-DD.")

        elif ft == "datetime":
            val_str = str(value).strip()
            try:
                datetime.datetime.fromisoformat(val_str.replace("Z", "+00:00"))
                return val_str
            except ValueError:
                raise BoconicException(code=ErrorCode.VALIDATION_ERROR, message=f"'{definition.label}' phải là ISO 8601 datetime.")

        elif ft == "single_select":
            val_str = str(value).strip()
            allowed = [opt.get("id") for opt in (definition.options or [])]
            if val_str not in allowed:
                raise BoconicException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"Giá trị '{val_str}' không nằm trong danh sách lựa chọn cho '{definition.label}'.",
                )
            return val_str

        elif ft == "multi_select":
            if isinstance(value, str):
                val_list = [v.strip() for v in value.split(",") if v.strip()]
            elif isinstance(value, list):
                val_list = [str(v).strip() for v in value]
            else:
                raise BoconicException(code=ErrorCode.VALIDATION_ERROR, message=f"'{definition.label}' phải là danh sách lựa chọn.")
            allowed = [opt.get("id") for opt in (definition.options or [])]
            for v in val_list:
                if v not in allowed:
                    raise BoconicException(
                        code=ErrorCode.VALIDATION_ERROR,
                        message=f"Giá trị '{v}' không hợp lệ cho '{definition.label}'.",
                    )
            return val_list

        elif ft == "url":
            val_str = str(value).strip()
            if not URL_REGEX.match(val_str):
                raise BoconicException(code=ErrorCode.VALIDATION_ERROR, message=f"'{definition.label}' phải là URL hợp lệ.")
            return val_str

        elif ft == "email":
            val_str = str(value).strip().lower()
            if not EMAIL_REGEX.match(val_str):
                raise BoconicException(code=ErrorCode.VALIDATION_ERROR, message=f"'{definition.label}' phải là email hợp lệ.")
            return val_str

        elif ft == "phone":
            val_str = str(value).strip()
            if not PHONE_REGEX.match(val_str):
                raise BoconicException(code=ErrorCode.VALIDATION_ERROR, message=f"'{definition.label}' phải là số điện thoại hợp lệ.")
            return val_str

        elif ft in ("image", "file"):
            return str(value).strip()

        elif ft == "json":
            if isinstance(value, (dict, list)):
                return value
            try:
                return json.loads(str(value))
            except Exception:
                raise BoconicException(code=ErrorCode.VALIDATION_ERROR, message=f"'{definition.label}' phải là JSON hợp lệ.")

        elif ft == "reference":
            return str(value).strip()

        return value

    @classmethod
    async def validate_custom_data(
        cls, db: AsyncSession, entity_type: str, custom_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        definitions = await cls.get_definitions_for_entity(db, entity_type, active_only=True)
        cleaned_data: Dict[str, Any] = {}

        for defn in definitions:
            raw_val = custom_data.get(defn.key)
            if raw_val is None and defn.default_value is not None:
                raw_val = defn.default_value
            val = cls.validate_field_value(defn, raw_val)
            if val is not None:
                cleaned_data[defn.key] = val

        return cleaned_data

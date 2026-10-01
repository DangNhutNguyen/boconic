# Boconic — Dynamic Custom Fields Architecture

**Version:** 2.0  
**Date:** 01/10/2026

## 1. Overview & Architecture

Administrators can add, modify, reorder, or archive business fields across key entities without modifying Python models or running Alembic DDL migrations.

Entities supporting custom fields:
- `Book` (e.g. `curriculum`, `series_volume`, `target_exam`)
- `BookCopy` (e.g. `shelf_location`, `physical_barcode`, `donor_name`)
- `User` (e.g. `preferred_contact_method`, `school_affiliation`)
- `Organization` (e.g. `library_code`, `operating_license`)
- `Loan` (e.g. `special_handover_notes`)
- `Resource` (e.g. `academic_peer_reviewed`, `digitization_quality`)

## 2. Storage Strategy
- Definitions stored in `custom_field_definitions`:
  - `id`: UUID primary key
  - `entity_type`: String (e.g., `"book"`, `"book_copy"`)
  - `key`: Alphanumeric slug (e.g., `"curriculum"`, unique per entity_type)
  - `label`: Human-readable label (e.g., `"Bộ sách / Chương trình"`)
  - `description`: Help text
  - `field_type`: String enum (16 types)
  - `required`: Boolean
  - `default_value`: JSON
  - `validation_rules`: JSON (e.g., min, max, regex, allowed_values)
  - `options`: JSON array for select types: `[{"id": "opt1", "label": "Kết nối tri thức"}, ...]`
  - `reference_entity`: Target entity for reference fields
  - `visibility`: `"public"`, `"internal"`, `"private"`
  - `sensitivity`: `"normal"`, `"pii"`, `"restricted"`
  - `display_order`: Integer
  - `active`: Boolean (false means archived/hidden from input forms, past values preserved)
- Entity tables contain a native JSONB column: `custom_data = Column(JSONB, default=dict)`.

## 3. Supported Field Types (16 Types)

| Field Type | Storage Format | Admin Widget | Validation Rules |
| :--- | :--- | :--- | :--- |
| `text` | String | Single-line `<input type="text">` | `min_length`, `max_length`, `regex` |
| `textarea` | String | Multi-line `<textarea>` | `max_length` |
| `integer` | Integer | `<input type="number" step="1">` | `min_value`, `max_value` |
| `decimal` | String / Decimal | `<input type="number" step="0.01">` | Preserves precision without float drift |
| `boolean` | Boolean | `<input type="checkbox">` | Must be boolean |
| `date` | ISO Date String (`YYYY-MM-DD`) | `<input type="date">` | Valid calendar date |
| `datetime` | ISO 8601 String | `<input type="datetime-local">` | Valid UTC datetime |
| `single_select` | Option ID string | `<select>` dropdown | Value must exist in definition `options` |
| `multi_select` | Array of Option IDs | Checkbox group / Multi-select | All values must exist in `options` |
| `url` | URL string | `<input type="url">` | Valid http/https scheme, SSRF check |
| `email` | Email string | `<input type="email">` | RFC-5322 format |
| `phone` | Phone string | `<input type="tel">` | Standard phone regex |
| `image` | Media File UUID string | File upload preview | MIME must be image/jpeg, image/png |
| `file` | Media File UUID string | Document upload | Enforces storage limits & extensions |
| `json` | Structured JSON dict/list | Code editor / JSON input | Max size (e.g. 10KB), depth <= 3 |
| `reference` | UUID of target entity | Searchable select picker | Entity must exist in allowlisted table |

## 4. Lifecycle & Safety Invariants
1. Changing an existing field type is forbidden if records already have populated data; field must be archived and a new one created.
2. Making a field `required` when historical records have null values does not break old records; it only enforces validation upon subsequent updates.
3. Archiving (`active = False`) retains all historical values in `custom_data` and maintains auditability.

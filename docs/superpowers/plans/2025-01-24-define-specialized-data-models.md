# Define Specialized Data Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define Pydantic models for "Layout Maps" and "Complex Extractions" to support structured data extraction from complex documents like 10-Ks.

**Architecture:** Use Pydantic V2 for schema definition. `LayoutMap` will describe the document structure, and `StructuredResponse` (updated) will hold the extracted financial data with context.

**Tech Stack:** Python, Pydantic, Pytest.

---

### Task 1: Define Layout Map Schema

**Files:**
- Create: `src/agents/structured_data_model/layout_map.py`
- Test: `tests/agents/structured_data_model/test_layout_map.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agents/structured_data_model/test_layout_map.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.structured_data_model.layout_map'`

- [ ] **Step 3: Write minimal implementation**

```python
from pydantic import BaseModel, Field
from typing import List

class LayoutComponent(BaseModel):
    type: str = Field(description="Type of component: table, text_block, list, footnote")
    description: str = Field(description="Description of the component content and logical role")
    coordinates_hint: str = Field(description="Natural language or approximate position hint (e.g. 'Top left', 'Bottom of page')")

class LayoutMap(BaseModel):
    components: List[LayoutComponent] = Field(description="List of structural components identified in the document")
    nested_table_count: int = Field(description="Number of complex or nested tables found")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/agents/structured_data_model/test_layout_map.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agents/structured_data_model/layout_map.py tests/agents/structured_data_model/test_layout_map.py
git commit -m "feat(topic-3): define layout map schema"
```

---

### Task 2: Update Generic Extraction Schema

**Files:**
- Modify: `src/agents/structured_data_model/generic_definition.py`
- Test: `tests/agents/structured_data_model/test_generic_definition.py`

- [ ] **Step 1: Write the failing test**

```python
from src.agents.structured_data_model.generic_definition import StructuredResponse, ExtractionItem

def test_generic_extraction_with_context():
    item = {
        "key": "Total Assets",
        "value": 1000000,
        "context": "As of Dec 31, 2024, per Item 8"
    }
    response = StructuredResponse(answer=[item])
    assert response.answer[0].key == "Total Assets"
    assert response.answer[0].context == "As of Dec 31, 2024, per Item 8"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agents/structured_data_model/test_generic_definition.py`
Expected: FAIL (either `context` missing or `answer` structure different)

- [ ] **Step 3: Write minimal implementation**

```python
from typing import Any, List
from pydantic import BaseModel, Field

class ExtractionItem(BaseModel):
    key: str = Field(description="The financial metric or field name")
    value: Any = Field(description="The extracted value")
    context: str = Field(description="Context or footnote reference for this value")

class StructuredResponse(BaseModel):
    \"\"\"Structured response for bank document extraction.\"\"\"
    answer: List[ExtractionItem] = Field(
        description="The extracted information in a list of contextualized items."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/agents/structured_data_model/test_generic_definition.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agents/structured_data_model/generic_definition.py tests/agents/structured_data_model/test_generic_definition.py
git commit -m "feat(topic-3): update generic extraction schema with context support"
```

# VSS Cloud Schema Change Request: Refinery Phase 1

## 1. Background & Objective
Refinery Phase 1 introduces **UUIDs** as the primary stable identifier for all media entities (Subtitles, Slices, Frames) to support vector indexing and human-in-the-loop workflows.

The Cloud Schemas must be updated to **persist these UUIDs** through the processing chain. This ensures that when data returns from the Cloud (e.g., after analysis or merging), the Edge system can correctly map results back to the local database entities.

## 2. Impacted Interfaces

| Service Slug | Schema File | Key Changes |
| :--- | :--- | :--- |
| `REFINERY_SUBTITLE_MERGER` | `subtitle_merger.py` | Add `id` (UUID) to SubtitleItem. |
| `REFINERY_CHARACTER_IDENTIFIER` | `character_identifier.py` | Add `id` (UUID) to SubtitleItem. |
| `REFINERY_SLICE_ANALYZER` | `slice_analyzer.py` | Replace `slice_id` (int) with `id` (UUID) + `index` (int). |
| `REFINERY_SLICE_REGROUPER` | `slice_regrouper.py` | Replace `slice_id` (int) with `id` (UUID) + `index` (int). |

## 3. Detailed Schema Changes

### 3.1 Subtitle Merger
**File**: `apps/common/schemas/refinery/subtitle_merger.py`

*   **SubtitleItem**:
    *   `+ id: Optional[str]`: UUID for tracking the subtitle line. Input and Output.

### 3.2 Character Identifier
**File**: `apps/common/schemas/refinery/character_identifier.py`

*   **SubtitleItem**:
    *   `+ id: Optional[str]`: UUID for tracking the subtitle line. Input only (Cloud uses it for context, returns updates referenced by index/id).

### 3.3 Slice Analyzer
**File**: `apps/common/schemas/refinery/slice_analyzer.py`

*   **SubtitleItem** (Nested in Slice):
    *   `+ id: Optional[str]`: UUID.
*   **MultimodalSlice** (Input):
    *   `- slice_id: int` (Removed)
    *   `+ id: str`: Slice UUID.
    *   `+ index: int`: Global sort order (0-based).
*   **AnalyzedSlice** (Output):
    *   `- slice_id: int` (Removed)
    *   `+ id: str`: Slice UUID.

### 3.4 Slice Regrouper
**File**: `apps/common/schemas/refinery/slice_regrouper.py`

*   **SubtitleItem** (Nested in Slice):
    *   `+ id: Optional[str]`: UUID.
*   **MultimodalSlice** (Input):
    *   `- slice_id: int` (Removed)
    *   `+ id: str`: Slice UUID.
    *   `+ index: int`: Global sort order (0-based).

## 4. Action Items for Cloud Team

1.  **Update Pydantic Models**: Apply the above field changes to the Cloud codebase.
2.  **Logic Adaptation**:
    *   **Subtitle Merger**: Ensure `id` is preserved where possible. If merging multiple lines, generate a new UUID for the merged line.
    *   **Slice Analyzer**: Ensure the output `AnalyzedSlice` carries the same `id` as the input `MultimodalSlice`.
    *   **Slice Regrouper**: Ensure the output `Scene` references slices by their UUIDs (if applicable in future logic), though currently it groups by content.

## 5. Compatibility Note

*   **Backward Compatibility**: The Edge client will start sending these fields immediately. Cloud endpoints should be configured to `ignore` extra fields if the deployment is not atomic, OR Cloud must be deployed first.
*   **Validation**: Edge client expects these fields to be present in the response for correct data hydration.
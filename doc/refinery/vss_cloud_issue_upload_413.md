# VSS Cloud Issue Report: 413 Request Entity Too Large on File Upload

## 1. Issue Summary
The VSS Edge client encounters a `413 Client Error: Request Entity Too Large` when uploading generated JSON metadata files to the VSS Cloud via the `/api/v1/files/upload` endpoint.

This blocks the `REFINERY_VISUAL_ANALYZER` pipeline step for long videos or videos with high frame density.

## 2. Technical Details

*   **Endpoint**: `POST /api/v1/files/upload`
*   **Client**: VSS Edge (Python `requests` library)
*   **Error Code**: `413`
*   **Error Message**: `Request Entity Too Large`
*   **Context**:
    *   The `VisualAnalyzerService` on Edge extracts keyframes and generates a JSON file containing metadata (frame IDs, cloud paths, digests) for all frames.
    *   This JSON file is uploaded to Cloud to initiate the visual analysis task.
    *   For a typical long video (e.g., 45 mins), this JSON file can exceed **1MB - 5MB**.

## 3. Root Cause Analysis
The error code `413` indicates that the VSS Cloud server (likely the Nginx Gateway, Ingress Controller, or the Application Server itself) has a configured `client_max_body_size` (or equivalent) that is too small for the operational requirements.

Common default limits are often set to **1MB**, which is insufficient for batch metadata uploads in video processing workflows.

## 4. Request for Change (RFC)

**Action Required**: Increase the maximum allowed request body size for the file upload endpoint.

**Recommended Configuration**:
*   **Target Limit**: **50MB** or **100MB** (to safely accommodate metadata for feature-length movies).

### Configuration Examples (Reference)

**Nginx / Ingress Nginx**:
```nginx
client_max_body_size 100m;
```

**Spring Boot / Java (if applicable)**:
```properties
spring.servlet.multipart.max-file-size=100MB
spring.servlet.multipart.max-request-size=100MB
```

## 5. Impact
Until this limit is increased, VSS Edge cannot process long-form content without implementing complex and undesirable workarounds (client-side chunking).
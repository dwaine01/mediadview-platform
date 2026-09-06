# TEST AGENT PROMPT – IMAGE INTEGRATION RULES

You are the Test Agent responsible for validating image integrations.
Follow these rules exactly. Do not overcomplicate.

## Image Handling Rules
- Always use base64-encoded images for all tests and requests.
- Accepted formats: JPEG, PNG, WEBP only.
- Do not use SVG, BMP, HEIC, or other formats.
- Do not upload blank, solid-color, or uniform-variance images.
- Every image must contain real visual features — such as objects, edges, textures, or shadows.
- If the image is not PNG/JPEG/WEBP, transcode it to PNG or JPEG before upload.
  ### Fix Example:
  If you read a .jpg but the content is actually PNG after conversion or compression — this is invalid.
  Always re-detect and update the MIME after transformations.
- If the image is animated (e.g., GIF, APNG, WEBP animation), extract the first frame only.
- Resize large images to reasonable bounds (avoid oversized payloads).

## Project note (MediaView)
The AI menu import endpoint is `POST /api/workspace/menus/ai-import` and expects
`{"image_base64": "<raw base64, no data: prefix>", "content_type": "image/jpeg"}`.
It uses the Emergent LLM key with OpenAI `gpt-5.4` (vision) and returns
`{menu_name, currency, items: [{name, price, description, category}], raw_count}`.
It does NOT write to the database — the customer confirms the extracted items and
then the existing `POST /api/workspace/menus` creates the menu.

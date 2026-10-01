# Reference-image editing and multi-reference synthesis

## Reference Role Mapping

Assign each reference only the roles the user actually wants to borrow. Common roles:

- **Identity**: face, hair, age impression, body identity.
- **Outfit**: garments, footwear, accessories.
- **Pose**: body posture, limb placement, gesture.
- **Expression/Gaze**: facial expression and viewing direction.
- **Composition**: crop, camera angle, subject placement, spatial arrangement.
- **Environment**: location, furniture, background objects.
- **Lighting/Color**: light direction, softness, time-of-day impression, palette.
- **Style/Medium**: photographic or illustrative rendering language.

Do not treat a reference as an all-or-nothing source.

## Preserve / Change / Ignore

Translate the request into three buckets before composing the final prompt.

Example input: "Keep image 1's person and clothes, use image 2's pose, keep image 1's background."

Internal mapping:
- Preserve: image 1 identity, hair, body characteristics, outfit, background.
- Change: pose to image 2.
- Ignore: image 2 identity, outfit, background, lighting unless separately requested.

Final prompt should state both the desired transfer and the boundaries of that transfer.

## Default priority for identity-preserving edits

When not otherwise specified:
1. Identity consistency
2. Explicit requested change
3. Anatomical/spatial coherence
4. Composition
5. Outfit details
6. Background details

Adjust this order when the user's request clearly emphasizes something else.

## Multi-reference examples

Input: "Image 1 uses image 2's pose. Don't look at the screen."

Resolve as:
- Image 1: Identity + any unspecified appearance baseline.
- Image 2: Pose only.
- Change gaze independently: subject does not look at a screen.
- Ignore image 2's identity, outfit, environment, and gaze unless requested.

Input: "Use person from image 1, outfit from image 2, composition from image 3."

Resolve as:
- Image 1 = Identity.
- Image 2 = Outfit.
- Image 3 = Composition/camera framing.
- Preserve image 1's identity while preventing image 2/3 identities from transferring.
- Do not inherit backgrounds from image 2 or 3 unless requested.

## Editing discipline

For follow-up edits, change only the requested dimension whenever possible. If the user says "raise the camera a little," preserve identity, outfit, pose, environment, expression, and lighting unless the new camera position logically requires a minor adjustment.

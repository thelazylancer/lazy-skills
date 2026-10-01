---
name: image-prompt-engineer
description: "Convert natural-language image requests and one or more reference images into clear, conflict-free, generation-ready prompts. Use for text-to-image prompt writing, single-reference edits, multi-reference composition such as keeping the person from image 1 while taking pose/outfit/composition from other images, realistic people photography prompts, thumbnails, diagrams, and prompt refinement. Also use when the user asks to directly generate an image; first resolve the image specification, then generate when image generation is available."
---

# Image Prompt Engineer

Turn the user's intent into the smallest complete image specification that a generation model can reliably follow.

## Core workflow

1. Identify the task: text-to-image, reference edit, multi-reference synthesis, thumbnail/text image, diagram, or prompt refinement.
2. Map every reference image to an explicit role before writing the prompt. For multi-reference work, use the Reference Role Mapping rules in `references/reference-editing.md`.
3. Separate requirements into:
   - **Preserve**: must remain unchanged or visually consistent.
   - **Change**: must be introduced or modified.
   - **Ignore**: elements from references that must not transfer.
4. Resolve conflicts before writing. Prefer concrete visible states over abstract adjectives and negative instructions.
5. Establish priority. Unless the user states otherwise, infer the order from the task; for identity-preserving edits, normally prioritize identity consistency before pose/composition/background.
6. Write the final prompt in a visually executable order: purpose/style -> subject -> clothing/objects -> action -> environment -> camera/composition -> light/texture -> priority/constraints.
7. Keep the output concise. Do not expose internal analysis unless the user asks for it or a material ambiguity/conflict needs explanation.

## Output behavior

- Default: return only the polished, copy-ready prompt, with a short note only when useful.
- If the user asks for analysis, show a compact specification first, then the final prompt.
- If the user explicitly asks to generate/create/render the image and an image-generation tool is available, use the resolved specification to generate it rather than stopping at a prompt.
- Preserve the user's requested language. If no language is specified, use the language of the request.
- Do not invent important subject attributes when references already establish them.

## General prompt rules

- Describe observable visual facts instead of relying on words such as "natural", "realistic", "beautiful", or "high quality" alone.
- Distinguish camera position, subject orientation, framing, and gaze.
- Distinguish body shape from garment fit.
- Distinguish selfie, mirror selfie, and third-person photography; keep the physical camera/phone relationship coherent.
- For casual phone photography, do not simulate realism merely by piling on blur, noise, bad exposure, pores, or camera defects. Specify plausible lighting, framing, environment visibility, and restrained imperfections.
- Prefer positive spatial instructions ("right hand holds the cup handle") to vague negatives ("no weird hands"). Use negative constraints only where they prevent unwanted transfer or additions.
- Avoid mutually exclusive requirements. If a conflict cannot be resolved from context and materially changes the result, ask one concise clarification question.
- Do not over-specify facial anatomy when a reference image is the identity source.

## Task-specific guidance

For people photography, read `references/people-photography.md`.

For any reference-image edit or multi-image synthesis, read `references/reference-editing.md`.

For thumbnails or images containing exact text, read `references/text-images.md`.

## Quality check

Before returning the prompt, silently verify:

- Every reference has one or more clear roles.
- Preserve/Change/Ignore requirements do not conflict.
- Camera position, subject direction, gaze, and crop can coexist physically.
- The prompt states the most important condition explicitly when the task is complex.
- Unrequested attributes from secondary references are prevented from leaking into the result.
- The prompt is no longer than necessary to express the intended image.

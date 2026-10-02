# Open-source components

## AI models

| Model | Used for | Licence | Note |
|-------|----------|---------|------|
| [Grounding DINO](https://huggingface.co/IDEA-Research/grounding-dino-tiny) (tiny) | Find building parts from text prompts | Apache 2.0 | |
| [Segment Anything (SAM)](https://huggingface.co/facebook/sam-vit-base) (ViT-B) | Outline each part | Apache 2.0 | |
| [Depth Pro](https://huggingface.co/apple/DepthPro-hf) | Metric depth + focal length (scale fallback) | Apple model licence | Check the terms before commercial use; it can be turned off (`models.depth = "mock"`), and the user measurement and reference-size scales do not need it |
| [SDXL inpainting 0.1](https://huggingface.co/diffusers/stable-diffusion-xl-1.0-inpainting-0.1) | Photorealistic redesign | CreativeML Open RAIL++-M | Use restrictions apply to generated content |
| [ControlNet Canny SDXL](https://huggingface.co/diffusers/controlnet-canny-sdxl-1.0) | Keeps the house's structure in the render | Open RAIL++-M | |

All models are used as published, without fine-tuning, through Hugging Face `transformers` and
`diffusers`.

## Libraries

| Library | Used for |
|---------|----------|
| FastAPI, Uvicorn, Pydantic | Backend and AI service APIs |
| PyTorch, transformers, diffusers, accelerate | Running the models |
| OpenCV, NumPy, Pillow | Image processing, masks, textures |
| ReportLab | PDF report |
| httpx, PyJWT | Supabase Data API / Storage calls, token verification |
| React, Vite, Tailwind CSS, lucide-react, supabase-js, axios | Frontend |
| Supabase (Postgres, Auth, Storage) | Hosted database, sign-in and file storage |

## Rate data
CPWD Delhi Schedule of Rates (DSR) 2021, items 13.46.1, 13.45.1 and 13.1, as indicative values.

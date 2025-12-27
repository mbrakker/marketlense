"""
Configuration for the pdf_to_html converter (Marker CLI knobs).

Edit this file to change Marker and OpenAI options. Do NOT store secrets here.
OpenAI API key must be provided via environment variable (default: OPENAI_API_KEY) or a .env file.
"""
from typing import Any, Dict, Optional

# OpenAI/OpenAI-compatible model to use
openai_model: str = "gpt-4.1"

# Optional OpenAI base URL (for API-compatible endpoints). Set to None to skip.
openai_base_url: Optional[str] = None

# Environment variable name that contains the OpenAI API key
openai_api_env: str = "OPENAI_API_KEY"

# LLM service class for Marker
llm_service: str = "marker.services.openai.OpenAIService"

# Default output directory when CLI --output-dir not provided
output_dir: str = "./out"

# Optional prompt to pass to Marker for block correction. Keep None by default.
# Example strict prompt (commented):
# block_correction_prompt = (
#     "When fixing OCR blocks, preserve numeric tables exactly and do not invent data."
# )
block_correction_prompt: Optional[str] = None

# Marker optional flags exposed to the converter. All are optional and off by default.
# Keys map to CLI flag names (snake_case -> --snake-case). Values:
# - bool True -> include flag --flag
# - str/int -> include --flag value
# - None or False -> omitted
marker_options: Dict[str, Any] = {
    # OCR-related
    "force_ocr": False,
    "strip_existing_ocr": False,
    # Output
    "paginate_output": False,
    "redo_inline_math": False,
    # Diagnostics
    "debug": False,
    "verbose": False,
}

# user_masters/ai/openai_service.py
"""
Backwards-compatible entrypoint wrapper.
Re-exports refactored extraction, merging, and validation functions from
modular subcomponents.
"""

from ai.extraction import openai_extract_users, apply_ai_smart_context
from extraction.local import local_extract_users
from extraction.merge import _merge_duplicate_users
from validation.validator import validate_master_data
from extraction.utils import find_matching_excel_roles, get_all_api_keys

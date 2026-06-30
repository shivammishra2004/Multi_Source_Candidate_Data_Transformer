import logging
import re
from typing import Dict, Any, List, Optional
from .models import CanonicalProfile
from .normalizer import Normalizer

logger = logging.getLogger(__name__)

class Projector:
    def __init__(self, config: Dict[str, Any] = None):
        """
        Optional config in init to support older patterns, but tests use project(profiles, config).
        """
        self.config = config or {}

    def _resolve_path(self, data: dict, path: str) -> Any:
        """
        Resolves nested dot notation, array indices (e.g., 'emails[0]', 'location.city'),
        and array map notation (e.g., 'skills[].name').
        """
        keys = path.split('.')
        current = data
        for k in keys:
            if current is None: 
                return None
            
            # Check for array map, e.g., 'skills[]'
            if k.endswith("[]"):
                array_key = k[:-2]
                if isinstance(current, dict) and array_key in current:
                    arr = current.get(array_key)
                    if not isinstance(arr, list):
                        return None
                    # We are in map mode. The rest of the keys apply to each item.
                    # Since this is a simple implementation, we just handle the immediate next key.
                    # This handles 'skills[].name'
                    rest_path = '.'.join(keys[keys.index(k)+1:])
                    if not rest_path:
                        return arr
                    return [self._resolve_path(item, rest_path) for item in arr if isinstance(item, dict)]
                return None

            # Check for array index, e.g., 'emails[0]'
            match = re.match(r'(.+)\[(\d+)\]', k)
            if match:
                array_key = match.group(1)
                idx = int(match.group(2))
                if isinstance(current, dict) and array_key in current:
                    arr = current.get(array_key)
                    if isinstance(arr, list) and len(arr) > idx:
                        current = arr[idx]
                    else:
                        return None
                else:
                    return None
            else:
                if isinstance(current, dict) and k in current:
                    current = current.get(k)
                else:
                    return None
        return current

    def project(self, profiles: List[CanonicalProfile], config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Projects a list of profiles according to the given config schema.
        Returns a dict: {"candidates": [dict, dict, ...]}
        """
        active_config = config if config is not None else self.config
        global_on_missing = active_config.get("on_missing", "null")
        include_confidence = active_config.get("include_confidence", True)
        include_provenance = active_config.get("include_provenance", True)
        fields_config = active_config.get("fields")
        
        candidates = []
        for profile in profiles:
            raw_dict = profile.to_dict()
            
            if fields_config is None:
                # Default schema: include everything, but clean up based on toggles
                result = raw_dict.copy()
            else:
                result = {}
                for field_def in fields_config:
                    if isinstance(field_def, str):
                        target_path = field_def
                        source_path = field_def
                        required = False
                    else:
                        target_path = field_def.get("path")
                        source_path = field_def.get("from", target_path)
                        required = field_def.get("required", False)
                        
                    val = self._resolve_path(raw_dict, source_path)
                    
                    is_empty = val is None or (isinstance(val, list) and len(val) == 0) or (isinstance(val, dict) and not any(val.values()))
                    
                    if not is_empty and isinstance(field_def, dict):
                        normalize_rule = field_def.get("normalize")
                        if normalize_rule == "E164":
                            val = Normalizer.format_phone(val)
                        elif normalize_rule == "canonical":
                            if isinstance(val, list):
                                val = list(Normalizer.normalize_skills(val))
                            elif isinstance(val, str):
                                val = Normalizer.normalize_skill(val)

                        expected_type = field_def.get("type")
                        if expected_type:
                            try:
                                if expected_type == "string" and not isinstance(val, str):
                                    val = str(val)
                                elif expected_type == "number" and not isinstance(val, (int, float)):
                                    val = float(val)
                                elif expected_type == "string[]":
                                    if not isinstance(val, list):
                                        val = [str(val)]
                                    else:
                                        val = [str(v) for v in val]
                            except (ValueError, TypeError):
                                if field_def.get("on_missing", global_on_missing) == "error" and required:
                                    raise ValueError(f"Type mismatch for {source_path}: expected {expected_type}")
                                is_empty = True
                                val = None

                    # Re-evaluate is_empty after normalization and typing
                    is_empty = val is None or (isinstance(val, list) and len(val) == 0) or (isinstance(val, dict) and not any(val.values()))
                    
                    if is_empty:
                        on_missing = field_def.get("on_missing", global_on_missing) if isinstance(field_def, dict) else global_on_missing
                        # We only throw error if required=True and on_missing="error", OR if on_missing="error" applies to all.
                        # Actually the tests imply on_missing="error" triggers if required=True
                        if on_missing == "error" and required:
                            raise ValueError(f"Required field '{source_path}' is missing.")
                        elif on_missing == "omit":
                            continue
                        elif on_missing == "null":
                            result[target_path] = None
                        else:
                            # if on_missing is error but not required, we can omit or null? 
                            # Let's just null it by default.
                            result[target_path] = None
                    else:
                        result[target_path] = val

            # Handle toggles for both custom and default schemas
            if include_confidence:
                result["overall_confidence"] = raw_dict.get("overall_confidence", 0.0)
            elif "overall_confidence" in result:
                del result["overall_confidence"]
                
            if include_provenance:
                result["provenance"] = raw_dict.get("provenance", [])
            elif "provenance" in result:
                del result["provenance"]

            candidates.append(result)

        return {"candidates": candidates}

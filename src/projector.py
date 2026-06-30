import logging
import re
from typing import Dict, Any, List, Optional
from .models import CanonicalProfile

logger = logging.getLogger(__name__)

class Projector:
    def __init__(self, config: Dict[str, Any]):
        """
        config example:
        {
          "fields": [
            { "path": "full_name", "required": true },
            { "path": "primary_email", "from": "emails[0]", "required": true },
            { "path": "city", "from": "location.city" },
            { "path": "skills" }
          ],
          "include_confidence": true,
          "on_missing": "null" # null, omit, error
        }
        """
        self.config = config

    def project_batch(self, profiles: List[CanonicalProfile]) -> List[Dict[str, Any]]:
        projected = []
        for p in profiles:
            try:
                proj_p = self.project(p)
                if proj_p is not None:
                    projected.append(proj_p)
            except ValueError as e:
                # If on_missing="error" is triggered, we drop the profile from the batch and log it.
                logger.error(f"Dropping profile {p.full_name} due to projection error: {e}")
        return projected

    def _resolve_path(self, data: dict, path: str) -> Any:
        """
        Resolves nested dot notation and array indices (e.g., 'emails[0]', 'location.city').
        """
        keys = path.split('.')
        current = data
        for k in keys:
            if current is None: 
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

    def project(self, profile: CanonicalProfile) -> Dict[str, Any]:
        global_on_missing = self.config.get("on_missing", "null")
        include_confidence = self.config.get("include_confidence", True)
        fields_config = self.config.get("fields", [])
        
        raw_dict = profile.to_dict()
        result = {}
        
        for field_def in fields_config:
            if isinstance(field_def, str):
                # Simple string inclusion in fields list
                target_path = field_def
                source_path = field_def
                required = False
            else:
                target_path = field_def.get("path")
                source_path = field_def.get("from", target_path)
                required = field_def.get("required", False)
                
            val = self._resolve_path(raw_dict, source_path)
            
            # Check if empty
            is_empty = val is None or (isinstance(val, list) and len(val) == 0) or (isinstance(val, dict) and not any(val.values()))
            
            if is_empty:
                on_missing = field_def.get("on_missing", global_on_missing)
                if required or on_missing == "error":
                    raise ValueError(f"Required field '{source_path}' is missing.")
                elif on_missing == "omit":
                    continue
                else:
                    result[target_path] = None
            else:
                result[target_path] = val
                
        # Toggle Metadata
        if include_confidence:
            result["provenance"] = raw_dict.get("provenance", [])
            result["overall_confidence"] = raw_dict.get("overall_confidence", 0.0)
                
        return result

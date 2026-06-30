import logging
from typing import List, Dict, Tuple
from .models import CanonicalProfile, Provenance, Skill
from .normalizer import Normalizer

logger = logging.getLogger(__name__)

class MergeEngine:
    def __init__(self, variance_penalty: float = 0.05):
        """
        :param variance_penalty: Amount to deduct from overall_confidence for each field conflict.
        """
        self.variance_penalty = variance_penalty

    def merge(self, sources_data: List[Tuple[List[CanonicalProfile], float]]) -> List[CanonicalProfile]:
        """
        Adapter for the older tuple format used in tests.
        """
        batch_data = []
        for i, (profiles, weight) in enumerate(sources_data):
            batch_data.append((f"Source_{i+1}", weight, profiles))
        return self.merge_batch(batch_data)

    def merge_batch(self, sources_data: List[Tuple[str, float, List[CanonicalProfile]]]) -> List[CanonicalProfile]:
        """
        Merges an arbitrary number of profile lists based on exact email match.
        :param sources_data: List of tuples (source_name, weight, profiles_list)
        """
        if not sources_data:
            return []

        # Start with the first source
        current_src_name, current_weight, current_profiles = sources_data[0]
        current_profiles = self._deduplicate_list(current_profiles, current_src_name, current_weight)
        
        # Apply standalone provenance to the first source
        for p in current_profiles:
            p.overall_confidence = current_weight
            p.provenance = []
            self._add_provenance_for_standalone(p, current_weight, current_src_name)

        # Iteratively fold in other sources
        for next_src_name, next_weight, next_profiles in sources_data[1:]:
            next_profiles = self._deduplicate_list(next_profiles, next_src_name, next_weight)
            
            for p in next_profiles:
                p.overall_confidence = next_weight
                p.provenance = []
                self._add_provenance_for_standalone(p, next_weight, next_src_name)
                
            current_profiles = self._merge_profile_lists(
                current_profiles, next_profiles, 
                current_src_name, next_src_name
            )
            # Update current source name to reflect the combination
            current_src_name = f"{current_src_name}+{next_src_name}"
            
        return current_profiles

    def _deduplicate_list(self, profiles: List[CanonicalProfile], src_name: str, weight: float) -> List[CanonicalProfile]:
        merged_no_email = []
        map1: Dict[str, CanonicalProfile] = {}
        github_map: Dict[str, CanonicalProfile] = {}
        
        for p in profiles:
            matched = None
            for email in p.emails:
                norm_email = Normalizer.normalize_email(email)
                if norm_email and norm_email in map1:
                    matched = map1[norm_email]
                    break
            
            if not matched and p.links.github:
                norm_github = Normalizer.normalize_url(p.links.github)
                if norm_github and norm_github in github_map:
                    matched = github_map[norm_github]
            
            if matched:
                new_merged = self._merge_two(matched, weight, src_name, p, weight, src_name)
                for email in new_merged.emails:
                    norm = Normalizer.normalize_email(email)
                    if norm:
                        map1[norm] = new_merged
                if new_merged.links.github:
                    norm_github = Normalizer.normalize_url(new_merged.links.github)
                    if norm_github:
                        github_map[norm_github] = new_merged
            else:
                has_key = False
                for email in p.emails:
                    norm = Normalizer.normalize_email(email)
                    if norm:
                        map1[norm] = p
                        has_key = True
                if p.links.github:
                    norm_github = Normalizer.normalize_url(p.links.github)
                    if norm_github:
                        github_map[norm_github] = p
                        has_key = True
                if not has_key:
                    merged_no_email.append(p)
                    
        unique_profiles = []
        seen = set()
        for p in list(map1.values()) + list(github_map.values()):
            if id(p) not in seen:
                seen.add(id(p))
                unique_profiles.append(p)
                
        return unique_profiles + merged_no_email

    def _merge_profile_lists(self, list1: List[CanonicalProfile], list2: List[CanonicalProfile], 
                             src1_name: str, src2_name: str) -> List[CanonicalProfile]:
        map1: Dict[str, CanonicalProfile] = {}
        github_map1: Dict[str, CanonicalProfile] = {}
        for p in list1:
            for email in p.emails:
                norm_email = Normalizer.normalize_email(email)
                if norm_email:
                    map1[norm_email] = p
            if p.links.github:
                norm_github = Normalizer.normalize_url(p.links.github)
                if norm_github:
                    github_map1[norm_github] = p
                    
        merged_profiles = []
        list1_processed_ids = set()
        
        for p2 in list2:
            matched_p1 = None
            for email in p2.emails:
                norm_email = Normalizer.normalize_email(email)
                if norm_email and norm_email in map1:
                    matched_p1 = map1[norm_email]
                    break
                    
            if not matched_p1 and p2.links.github:
                norm_github = Normalizer.normalize_url(p2.links.github)
                if norm_github and norm_github in github_map1:
                    matched_p1 = github_map1[norm_github]
            
            if matched_p1:
                w1 = getattr(matched_p1, 'overall_confidence', 1.0)
                w2 = getattr(p2, 'overall_confidence', 1.0)
                merged = self._merge_two(matched_p1, w1, src1_name, p2, w2, src2_name)
                merged_profiles.append(merged)
                list1_processed_ids.add(id(matched_p1))
            else:
                merged_profiles.append(p2)
                
        for p1 in list1:
            if id(p1) not in list1_processed_ids:
                merged_profiles.append(p1)
                
        return merged_profiles

    def _add_provenance_for_standalone(self, profile: CanonicalProfile, weight: float, source: str):
        fields = ['full_name', 'headline', 'years_experience']
        for f in fields:
            val = getattr(profile, f, None)
            if val:
                profile.provenance.append(Provenance(field=f, source=source, method="standalone", confidence=weight))
        
        if profile.location.city or profile.location.region or profile.location.country:
             profile.provenance.append(Provenance(field='location', source=source, method="standalone", confidence=weight))
             
        if profile.emails: profile.provenance.append(Provenance(field='emails', source=source, method="standalone", confidence=weight))
        if profile.phones: profile.provenance.append(Provenance(field='phones', source=source, method="standalone", confidence=weight))
        if profile.skills: profile.provenance.append(Provenance(field='skills', source=source, method="standalone", confidence=weight))

    def _merge_two(self, p1: CanonicalProfile, w1: float, src1: str, p2: CanonicalProfile, w2: float, src2: str) -> CanonicalProfile:
        merged = CanonicalProfile()
        conflicts = 0
        total_fields_merged = 0
        sum_confidence = 0.0

        def merge_scalar(field_name: str) -> None:
            nonlocal conflicts, total_fields_merged, sum_confidence
            v1 = getattr(p1, field_name, None)
            v2 = getattr(p2, field_name, None)
            
            if not v1 and not v2:
                return
            
            total_fields_merged += 1
            
            if v1 and not v2:
                setattr(merged, field_name, v1)
                merged.provenance.append(Provenance(field=field_name, source=src1, method="weight_fallback", confidence=w1))
                sum_confidence += w1
            elif v2 and not v1:
                setattr(merged, field_name, v2)
                merged.provenance.append(Provenance(field=field_name, source=src2, method="weight_fallback", confidence=w2))
                sum_confidence += w2
            else:
                # Both exist, resolve conflict deterministically
                if v1 != v2:
                    conflicts += 1
                    
                if w1 > w2:
                    winner_val, winner_src, winner_weight = v1, src1, w1
                elif w2 > w1:
                    winner_val, winner_src, winner_weight = v2, src2, w2
                else:
                    # Tie-breaker: string length (for strings)
                    if isinstance(v1, str) and isinstance(v2, str):
                        if len(v1) >= len(v2):
                            winner_val, winner_src, winner_weight = v1, src1, w1
                        else:
                            winner_val, winner_src, winner_weight = v2, src2, w2
                    else:
                        winner_val, winner_src, winner_weight = v1, src1, w1
                        
                setattr(merged, field_name, winner_val)
                merged.provenance.append(Provenance(field=field_name, source=winner_src, method="weight_resolution", confidence=winner_weight))
                sum_confidence += winner_weight

        # SCALARS
        merge_scalar('candidate_id')
        merge_scalar('full_name')
        merge_scalar('headline')
        merge_scalar('company')
        merge_scalar('years_experience')

        # LOCATION (pseudo-scalar object)
        loc1_has_data = p1.location.city or p1.location.region or p1.location.country
        loc2_has_data = p2.location.city or p2.location.region or p2.location.country
        if loc1_has_data and not loc2_has_data:
            merged.location = p1.location
            merged.provenance.append(Provenance(field='location', source=src1, method="weight_fallback", confidence=w1))
            total_fields_merged += 1; sum_confidence += w1
        elif loc2_has_data and not loc1_has_data:
            merged.location = p2.location
            merged.provenance.append(Provenance(field='location', source=src2, method="weight_fallback", confidence=w2))
            total_fields_merged += 1; sum_confidence += w2
        elif loc1_has_data and loc2_has_data:
            conflicts += 1
            total_fields_merged += 1
            if w1 >= w2:
                merged.location = p1.location
                merged.provenance.append(Provenance(field='location', source=src1, method="weight_resolution", confidence=w1))
                sum_confidence += w1
            else:
                merged.location = p2.location
                merged.provenance.append(Provenance(field='location', source=src2, method="weight_resolution", confidence=w2))
                sum_confidence += w2

        # LISTS (Set Union)
        
        # Emails
        emails_set = set()
        emails_list = []
        for em in p1.emails + p2.emails:
            norm = Normalizer.normalize_email(em)
            if norm and norm not in emails_set:
                emails_set.add(norm)
                emails_list.append(norm) # use normalized
        merged.emails = emails_list
        if emails_list:
            merged.provenance.append(Provenance(field='emails', source=f"{src1},{src2}", method="set_union", confidence=max(w1, w2)))
            
        # Phones
        phones_set = set()
        phones_list = []
        for ph in p1.phones + p2.phones:
            norm = Normalizer.format_phone(ph)
            if norm and norm not in phones_set:
                phones_set.add(norm)
                phones_list.append(norm)
        merged.phones = phones_list
        if phones_list:
            merged.provenance.append(Provenance(field='phones', source=f"{src1},{src2}", method="set_union", confidence=max(w1, w2)))

        # Skills
        skills_map = {}
        for s in p1.skills + p2.skills:
            norm_name = s.name.strip().lower()
            if not norm_name: continue
            
            src_origin = src1 if s in p1.skills else src2
            
            if norm_name in skills_map:
                if src_origin not in skills_map[norm_name].sources:
                    skills_map[norm_name].sources.append(src_origin)
            else:
                skills_map[norm_name] = Skill(name=norm_name, confidence=s.confidence, sources=[src_origin])
                
        merged.skills = list(skills_map.values())
        if merged.skills:
            merged.provenance.append(Provenance(field='skills', source=f"{src1},{src2}", method="set_union", confidence=max(w1, w2)))

        # Links (Scalar fallback for specific links, union for others)
        merged.links.github = p1.links.github or p2.links.github
        merged.links.linkedin = p1.links.linkedin or p2.links.linkedin
        merged.links.portfolio = p1.links.portfolio or p2.links.portfolio
        merged.links.other = list(set(p1.links.other + p2.links.other))

        # Experience & Education (Simple list union for now)
        merged.experience = p1.experience + p2.experience
        merged.education = p1.education + p2.education

        # OVERALL CONFIDENCE (Weighted Average - Variance Penalty)
        if total_fields_merged > 0:
            base_confidence = sum_confidence / total_fields_merged
        else:
            base_confidence = max(w1, w2)
            
        penalty = conflicts * self.variance_penalty
        merged.overall_confidence = max(0.0, min(1.0, base_confidence - penalty))

        return merged

"""Implication suggestion data model."""


class ImplicationSuggestion:
    """Represents a suggested tag implication."""
    def __init__(self, source_tag: str, implied_tag: str, confidence: float,
                 pattern_type: str, reason: str, affected_images: int = 0,
                 sample_size: int = 0,
                 source_category: str = 'general', implied_category: str = 'general'):
        self.source_tag = source_tag
        self.implied_tag = implied_tag
        self.confidence = confidence
        self.pattern_type = pattern_type
        self.reason = reason
        self.affected_images = affected_images
        self.sample_size = sample_size
        self.source_category = source_category
        self.implied_category = implied_category

    def to_dict(self):
        return {
            'source_tag': self.source_tag,
            'implied_tag': self.implied_tag,
            'confidence': self.confidence,
            'pattern_type': self.pattern_type,
            'reason': self.reason,
            'affected_images': self.affected_images,
            'sample_size': self.sample_size,
            'source_category': self.source_category,
            'implied_category': self.implied_category
        }

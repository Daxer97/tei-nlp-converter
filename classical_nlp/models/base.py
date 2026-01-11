"""
Base classes for Classical NLP Providers

Defines the abstract interface that all classical NLP providers must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum


class ProviderStatus(Enum):
    """Provider availability status."""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    INITIALIZING = "initializing"


@dataclass
class BotanicalTerm:
    """
    Represents a botanical term found in text.

    Used for the Virgil/Botanical project to track plant references.
    """
    text: str  # Original form in text
    lemma: str  # Dictionary form
    scientific_name: Optional[str] = None  # Modern scientific name
    common_name: Optional[str] = None  # Common name
    start_char: int = 0
    end_char: int = 0
    occurrences: int = 1
    positions: List[str] = field(default_factory=list)  # Section references


@dataclass
class TokenInfo:
    """Detailed information about a token."""
    text: str
    lemma: str
    pos: str  # Part of speech
    morph: str = ""  # Morphological features (case, number, gender, tense, etc.)
    dep: str = ""  # Dependency relation
    head: int = -1  # Head token index
    idx: int = 0  # Character offset
    i: int = 0  # Token index
    is_punct: bool = False
    is_space: bool = False
    whitespace_: str = " "


@dataclass
class SentenceInfo:
    """Information about a sentence."""
    text: str
    tokens: List[TokenInfo]
    start_char: int = 0
    end_char: int = 0


@dataclass
class EntityInfo:
    """Named entity information."""
    text: str
    label: str
    start: int  # Token start
    end: int  # Token end
    start_char: int = 0
    end_char: int = 0
    kb_id: Optional[str] = None
    confidence: float = 1.0


@dataclass
class ClassicalProcessingResult:
    """
    Standardized result from classical NLP processing.

    Contains all linguistic annotations extracted from text.
    """
    text: str
    language: str
    model_used: str
    sentences: List[Dict[str, Any]]
    entities: List[Dict[str, Any]]
    tokens: List[Dict[str, Any]]
    dependencies: List[Dict[str, Any]]
    noun_chunks: List[Dict[str, Any]]
    botanical_terms: List[BotanicalTerm]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "text": self.text,
            "language": self.language,
            "model_used": self.model_used,
            "sentences": self.sentences,
            "entities": self.entities,
            "tokens": self.tokens,
            "dependencies": self.dependencies,
            "noun_chunks": self.noun_chunks,
            "botanical_terms": [
                {
                    "text": bt.text,
                    "lemma": bt.lemma,
                    "scientific_name": bt.scientific_name,
                    "common_name": bt.common_name,
                    "start_char": bt.start_char,
                    "end_char": bt.end_char,
                    "occurrences": bt.occurrences,
                    "positions": bt.positions
                }
                for bt in self.botanical_terms
            ],
            "metadata": self.metadata
        }


class ClassicalNLPProvider(ABC):
    """
    Abstract base class for Classical NLP providers.

    All classical language NLP providers must implement this interface.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the provider.

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self._status = ProviderStatus.INITIALIZING
        self._model = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Get provider name."""
        pass

    @property
    @abstractmethod
    def supported_languages(self) -> List[str]:
        """Get list of supported languages."""
        pass

    @property
    def status(self) -> ProviderStatus:
        """Get current provider status."""
        return self._status

    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the provider and load models.

        Returns:
            True if initialization successful
        """
        pass

    @abstractmethod
    async def process(self, text: str, options: Dict[str, Any] = None) -> ClassicalProcessingResult:
        """
        Process text and return NLP results.

        Args:
            text: Text to process
            options: Processing options

        Returns:
            ClassicalProcessingResult with all annotations
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if provider is healthy.

        Returns:
            True if provider is operational
        """
        pass

    async def close(self):
        """Clean up resources."""
        self._model = None
        self._status = ProviderStatus.UNAVAILABLE

    def get_capabilities(self) -> Dict[str, bool]:
        """Get provider capabilities."""
        return {
            "lemmatization": True,
            "pos_tagging": True,
            "morphology": True,
            "dependency_parsing": False,
            "entity_recognition": False,
            "botanical_detection": True,
            "metrical_analysis": False
        }


# Botanical terms database for Virgil/Latin texts
LATIN_BOTANICAL_TERMS = {
    # Vines and grapes
    "vitis": {"scientific": "Vitis vinifera", "common": "vite", "category": "vine"},
    "uva": {"scientific": "Vitis vinifera", "common": "uva", "category": "fruit"},
    "vinum": {"scientific": "Vitis vinifera", "common": "vino", "category": "product"},
    "vinea": {"scientific": "Vitis vinifera", "common": "vigna", "category": "cultivation"},
    "pampinus": {"scientific": "Vitis vinifera", "common": "pampino", "category": "plant_part"},

    # Trees
    "quercus": {"scientific": "Quercus spp.", "common": "quercia", "category": "tree"},
    "fagus": {"scientific": "Fagus sylvatica", "common": "faggio", "category": "tree"},
    "fraxinus": {"scientific": "Fraxinus excelsior", "common": "frassino", "category": "tree"},
    "ulmus": {"scientific": "Ulmus spp.", "common": "olmo", "category": "tree"},
    "pinus": {"scientific": "Pinus spp.", "common": "pino", "category": "tree"},
    "abies": {"scientific": "Abies alba", "common": "abete", "category": "tree"},
    "cupressus": {"scientific": "Cupressus sempervirens", "common": "cipresso", "category": "tree"},
    "laurus": {"scientific": "Laurus nobilis", "common": "alloro", "category": "tree"},
    "olea": {"scientific": "Olea europaea", "common": "olivo", "category": "tree"},
    "ficus": {"scientific": "Ficus carica", "common": "fico", "category": "tree"},
    "malus": {"scientific": "Malus domestica", "common": "melo", "category": "tree"},
    "pyrus": {"scientific": "Pyrus communis", "common": "pero", "category": "tree"},
    "prunus": {"scientific": "Prunus spp.", "common": "pruno", "category": "tree"},
    "platanus": {"scientific": "Platanus orientalis", "common": "platano", "category": "tree"},
    "populus": {"scientific": "Populus spp.", "common": "pioppo", "category": "tree"},
    "salix": {"scientific": "Salix spp.", "common": "salice", "category": "tree"},
    "tilia": {"scientific": "Tilia spp.", "common": "tiglio", "category": "tree"},
    "arbor": {"scientific": None, "common": "albero", "category": "generic_tree"},

    # Crops and grains
    "triticum": {"scientific": "Triticum aestivum", "common": "grano", "category": "grain"},
    "hordeum": {"scientific": "Hordeum vulgare", "common": "orzo", "category": "grain"},
    "avena": {"scientific": "Avena sativa", "common": "avena", "category": "grain"},
    "seges": {"scientific": None, "common": "messe", "category": "crop"},
    "messis": {"scientific": None, "common": "mietitura", "category": "crop"},
    "far": {"scientific": "Triticum dicoccum", "common": "farro", "category": "grain"},
    "frumentum": {"scientific": "Triticum spp.", "common": "frumento", "category": "grain"},

    # Herbs and plants
    "rosa": {"scientific": "Rosa spp.", "common": "rosa", "category": "flower"},
    "lilium": {"scientific": "Lilium candidum", "common": "giglio", "category": "flower"},
    "viola": {"scientific": "Viola odorata", "common": "viola", "category": "flower"},
    "narcissus": {"scientific": "Narcissus spp.", "common": "narciso", "category": "flower"},
    "crocus": {"scientific": "Crocus sativus", "common": "croco", "category": "flower"},
    "hyacinthus": {"scientific": "Hyacinthus orientalis", "common": "giacinto", "category": "flower"},
    "hedera": {"scientific": "Hedera helix", "common": "edera", "category": "climbing"},
    "acanthus": {"scientific": "Acanthus mollis", "common": "acanto", "category": "ornamental"},
    "thymus": {"scientific": "Thymus vulgaris", "common": "timo", "category": "herb"},
    "mentha": {"scientific": "Mentha spp.", "common": "menta", "category": "herb"},
    "ruta": {"scientific": "Ruta graveolens", "common": "ruta", "category": "herb"},
    "ferula": {"scientific": "Ferula communis", "common": "ferula", "category": "herb"},
    "cuminum": {"scientific": "Cuminum cyminum", "common": "cumino", "category": "spice"},
    "papaver": {"scientific": "Papaver somniferum", "common": "papavero", "category": "flower"},

    # Vegetables
    "brassica": {"scientific": "Brassica oleracea", "common": "cavolo", "category": "vegetable"},
    "lactuca": {"scientific": "Lactuca sativa", "common": "lattuga", "category": "vegetable"},
    "beta": {"scientific": "Beta vulgaris", "common": "bietola", "category": "vegetable"},
    "allium": {"scientific": "Allium spp.", "common": "aglio", "category": "vegetable"},
    "cepa": {"scientific": "Allium cepa", "common": "cipolla", "category": "vegetable"},
    "cucumis": {"scientific": "Cucumis sativus", "common": "cetriolo", "category": "vegetable"},
    "cucurbita": {"scientific": "Cucurbita spp.", "common": "zucca", "category": "vegetable"},
    "faba": {"scientific": "Vicia faba", "common": "fava", "category": "legume"},
    "lens": {"scientific": "Lens culinaris", "common": "lenticchia", "category": "legume"},
    "cicer": {"scientific": "Cicer arietinum", "common": "cece", "category": "legume"},

    # Agricultural terms
    "ager": {"scientific": None, "common": "campo", "category": "agriculture"},
    "arvum": {"scientific": None, "common": "campo arato", "category": "agriculture"},
    "pratum": {"scientific": None, "common": "prato", "category": "agriculture"},
    "hortus": {"scientific": None, "common": "orto", "category": "agriculture"},
    "silva": {"scientific": None, "common": "selva", "category": "environment"},
    "nemus": {"scientific": None, "common": "bosco", "category": "environment"},
    "lucus": {"scientific": None, "common": "bosco sacro", "category": "environment"},
}

# Greek botanical terms
GREEK_BOTANICAL_TERMS = {
    "ἄμπελος": {"scientific": "Vitis vinifera", "common": "vite", "category": "vine"},
    "σῖτος": {"scientific": "Triticum spp.", "common": "grano", "category": "grain"},
    "κριθή": {"scientific": "Hordeum vulgare", "common": "orzo", "category": "grain"},
    "ἐλαία": {"scientific": "Olea europaea", "common": "olivo", "category": "tree"},
    "δρῦς": {"scientific": "Quercus spp.", "common": "quercia", "category": "tree"},
    "πεύκη": {"scientific": "Pinus spp.", "common": "pino", "category": "tree"},
    "κυπάρισσος": {"scientific": "Cupressus sempervirens", "common": "cipresso", "category": "tree"},
    "δάφνη": {"scientific": "Laurus nobilis", "common": "alloro", "category": "tree"},
    "ῥόδον": {"scientific": "Rosa spp.", "common": "rosa", "category": "flower"},
    "κρίνον": {"scientific": "Lilium candidum", "common": "giglio", "category": "flower"},
    "ἴον": {"scientific": "Viola odorata", "common": "viola", "category": "flower"},
    "κισσός": {"scientific": "Hedera helix", "common": "edera", "category": "climbing"},
    "θύμος": {"scientific": "Thymus vulgaris", "common": "timo", "category": "herb"},
}

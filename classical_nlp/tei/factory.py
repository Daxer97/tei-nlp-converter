"""
TEI Generator Factory

Factory for creating appropriate TEI generators based on
language and model configuration.
"""

from typing import Dict, Any, Type, Optional
import logging

from .base import ClassicalTEIGenerator
from .latin_tei import LatinTEIGenerator
from .greek_tei import GreekTEIGenerator

logger = logging.getLogger(__name__)


class TEIGeneratorFactory:
    """
    Factory for creating TEI generators.

    Uses language and model information to select the appropriate
    TEI generator for the text being processed.
    """

    # Mapping of (language, model) to generator classes
    _generators: Dict[tuple, Type[ClassicalTEIGenerator]] = {
        ('latin', 'latincy'): LatinTEIGenerator,
        ('latin', 'cltk-latin'): LatinTEIGenerator,
        ('latin', 'cltk'): LatinTEIGenerator,
        ('la', 'latincy'): LatinTEIGenerator,
        ('la', 'cltk-latin'): LatinTEIGenerator,
        ('ancient_greek', 'cltk-greek'): GreekTEIGenerator,
        ('ancient_greek', 'cltk'): GreekTEIGenerator,
        ('grc', 'cltk-greek'): GreekTEIGenerator,
        ('grc', 'cltk'): GreekTEIGenerator,
    }

    # Default generators by language
    _default_generators: Dict[str, Type[ClassicalTEIGenerator]] = {
        'latin': LatinTEIGenerator,
        'la': LatinTEIGenerator,
        'ancient_greek': GreekTEIGenerator,
        'grc': GreekTEIGenerator,
    }

    @classmethod
    def create(
        cls,
        language: str,
        model: str = None,
        config: Dict[str, Any] = None
    ) -> ClassicalTEIGenerator:
        """
        Create a TEI generator for the specified language and model.

        Args:
            language: Language code ('latin', 'ancient_greek', etc.)
            model: NLP model ID (optional, for model-specific generation)
            config: Configuration dictionary for the generator

        Returns:
            ClassicalTEIGenerator instance

        Raises:
            ValueError: If no generator found for the language
        """
        language = language.lower()
        model = model.lower() if model else None

        # Try specific (language, model) combination first
        if model:
            key = (language, model)
            if key in cls._generators:
                generator_class = cls._generators[key]
                logger.debug(f"Using generator for ({language}, {model})")
                return generator_class(config)

        # Fall back to default for language
        if language in cls._default_generators:
            generator_class = cls._default_generators[language]
            logger.debug(f"Using default generator for {language}")
            return generator_class(config)

        raise ValueError(
            f"No TEI generator available for language '{language}'. "
            f"Supported languages: {list(cls._default_generators.keys())}"
        )

    @classmethod
    def register_generator(
        cls,
        language: str,
        model: str,
        generator_class: Type[ClassicalTEIGenerator]
    ):
        """
        Register a new generator for a language/model combination.

        Args:
            language: Language code
            model: Model ID
            generator_class: Generator class to register
        """
        key = (language.lower(), model.lower())
        cls._generators[key] = generator_class
        logger.info(f"Registered TEI generator for ({language}, {model})")

    @classmethod
    def get_available_generators(cls) -> Dict[str, list]:
        """
        Get list of available generators organized by language.

        Returns:
            Dictionary mapping languages to list of model-specific generators
        """
        result = {}

        for (lang, model), gen_class in cls._generators.items():
            if lang not in result:
                result[lang] = []
            result[lang].append({
                'model': model,
                'generator': gen_class.__name__
            })

        return result


def create_tei_generator(
    language: str,
    model: str = None,
    config: Dict[str, Any] = None
) -> ClassicalTEIGenerator:
    """
    Convenience function to create a TEI generator.

    Args:
        language: Language code ('latin', 'ancient_greek', etc.)
        model: NLP model ID (optional)
        config: Generator configuration

    Returns:
        ClassicalTEIGenerator instance
    """
    return TEIGeneratorFactory.create(language, model, config)

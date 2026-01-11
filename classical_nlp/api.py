"""
API Endpoints for Classical NLP Processing

FastAPI router for processing classical texts (Latin and Ancient Greek)
with specialized NLP models and TEI generation.
"""

from fastapi import APIRouter, HTTPException, Query, Response, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from enum import Enum
import io
import json
import logging
from datetime import datetime

from .language_detector import ClassicalLanguageDetector, ClassicalLanguage
from .models import ModelRegistry, get_provider_for_language, get_available_models
from .tei import create_tei_generator
from .search import OccurrenceSearcher, SearchConfig, SearchMode, SearchResult
from .export import HTMLReportGenerator

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v2/classical", tags=["Classical NLP"])


# Enums for API
class LanguageEnum(str, Enum):
    AUTO = "auto"
    LATIN = "latin"
    ANCIENT_GREEK = "ancient_greek"


class SearchModeEnum(str, Enum):
    EXACT = "exact"
    LEMMATIZED = "lemmatized"
    REGEX = "regex"
    FUZZY = "fuzzy"


# Request/Response Models
class ProcessRequest(BaseModel):
    """Request model for text processing."""
    text: str = Field(..., min_length=1, max_length=500000, description="Text to process")
    language: LanguageEnum = Field(
        default=LanguageEnum.AUTO,
        description="Language of the text (auto-detect if not specified)"
    )
    model: Optional[str] = Field(
        default=None,
        description="NLP model to use (auto-select if not specified)"
    )
    title: Optional[str] = Field(
        default="Classical Text",
        description="Document title for TEI header"
    )
    author: Optional[str] = Field(
        default=None,
        description="Document author for TEI header"
    )
    include_botanical: bool = Field(
        default=True,
        description="Include botanical term annotations"
    )

    @validator('text')
    def text_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Text cannot be empty")
        return v


class SearchRequest(BaseModel):
    """Request model for occurrence search."""
    query: str = Field(..., min_length=1, max_length=200, description="Search term or pattern")
    mode: SearchModeEnum = Field(
        default=SearchModeEnum.EXACT,
        description="Search mode"
    )
    words_before: int = Field(
        default=5, ge=0, le=20,
        description="Context words before match"
    )
    words_after: int = Field(
        default=5, ge=0, le=20,
        description="Context words after match"
    )
    fuzzy_threshold: float = Field(
        default=0.8, ge=0.5, le=1.0,
        description="Minimum similarity for fuzzy search"
    )
    max_results: int = Field(
        default=500, ge=1, le=2000,
        description="Maximum results to return"
    )


class BotanicalTermResponse(BaseModel):
    """Response model for botanical terms."""
    text: str
    lemma: str
    scientific_name: Optional[str]
    common_name: Optional[str]
    occurrences: int
    positions: List[str]


class ProcessResponse(BaseModel):
    """Response model for text processing."""
    tei_xml: str
    detected_language: str
    model_used: str
    word_count: int
    sentence_count: int
    botanical_terms: List[BotanicalTermResponse]
    processing_time_ms: float
    metadata: Dict[str, Any]


class SearchResultResponse(BaseModel):
    """Response model for a single search result."""
    word_found: str
    context_before: str
    context_after: str
    position: int
    line_number: int
    section_ref: Optional[str]
    lemma: Optional[str]
    pos_tag: Optional[str]
    match_score: float


class SearchResponse(BaseModel):
    """Response model for search results."""
    total_occurrences: int
    results: List[SearchResultResponse]
    statistics: Dict[str, Any]
    wordcloud_data: List[Dict[str, Any]]


class LanguageDetectionResponse(BaseModel):
    """Response model for language detection."""
    language: str
    confidence: float
    greek_char_ratio: float
    latin_char_ratio: float
    details: Dict[str, Any]


class ModelInfo(BaseModel):
    """Information about an NLP model."""
    id: str
    name: str
    description: str
    features: List[str]
    recommended_for: List[str]


class ModelsResponse(BaseModel):
    """Response model for available models."""
    latin: List[ModelInfo]
    ancient_greek: List[ModelInfo]


# Cache for processed documents (simple in-memory cache)
_document_cache: Dict[str, Dict[str, Any]] = {}


@router.post("/process", response_model=ProcessResponse)
async def process_classical_text(request: ProcessRequest):
    """
    Process classical text with specialized NLP.

    This endpoint:
    1. Detects the language (Latin or Ancient Greek) if not specified
    2. Selects the appropriate NLP model
    3. Processes the text with morphological analysis
    4. Generates TEI XML with linguistic annotations
    5. Extracts botanical terms (for Virgil project)

    Returns the TEI XML along with metadata and extracted information.
    """
    start_time = datetime.now()

    try:
        # Step 1: Detect language if auto
        if request.language == LanguageEnum.AUTO:
            detector = ClassicalLanguageDetector()
            detection = detector.detect(request.text)
            detected_language = detection.language.value

            if detected_language == "unknown":
                # Default to Latin for unknown
                detected_language = "latin"
                logger.warning("Could not detect language, defaulting to Latin")
        else:
            detected_language = request.language.value

        # Step 2: Get NLP provider
        provider = get_provider_for_language(
            language=detected_language,
            provider_id=request.model
        )

        # Initialize provider
        await provider.initialize()

        # Step 3: Process text
        nlp_result = await provider.process(request.text)

        # Step 4: Generate TEI
        tei_config = {
            'title': request.title,
            'author': request.author,
            'include_lemma': True,
            'include_pos': True,
            'include_morph': True
        }

        tei_generator = create_tei_generator(
            language=detected_language,
            model=request.model,
            config=tei_config
        )

        tei_xml = tei_generator.generate(nlp_result.to_dict())

        # Step 5: Extract botanical terms
        botanical_terms = []
        for bt in nlp_result.botanical_terms:
            botanical_terms.append(BotanicalTermResponse(
                text=bt.text,
                lemma=bt.lemma,
                scientific_name=bt.scientific_name,
                common_name=bt.common_name,
                occurrences=bt.occurrences,
                positions=bt.positions
            ))

        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        # Cache the result for search
        cache_key = str(hash(request.text))[:16]
        _document_cache[cache_key] = {
            'nlp_result': nlp_result.to_dict(),
            'text': request.text,
            'language': detected_language,
            'title': request.title
        }

        return ProcessResponse(
            tei_xml=tei_xml,
            detected_language=detected_language,
            model_used=nlp_result.model_used,
            word_count=len(nlp_result.tokens),
            sentence_count=len(nlp_result.sentences),
            botanical_terms=botanical_terms,
            processing_time_ms=processing_time,
            metadata={
                'cache_key': cache_key,
                'provider': provider.name,
                'capabilities': provider.get_capabilities()
            }
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing text: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")


@router.post("/search", response_model=SearchResponse)
async def search_occurrences(
    search: SearchRequest,
    cache_key: str = Query(..., description="Cache key from process response"),
):
    """
    Search for occurrences in a processed document.

    Requires the cache_key from a previous /process call.

    Search modes:
    - exact: Case-insensitive exact match
    - lemmatized: Find all forms with the same lemma
    - regex: Regular expression search
    - fuzzy: Approximate matching with similarity threshold
    """
    # Get cached document
    if cache_key not in _document_cache:
        raise HTTPException(
            status_code=404,
            detail="Document not found. Please process the text first using /process"
        )

    cached = _document_cache[cache_key]

    try:
        # Create searcher
        searcher = OccurrenceSearcher(document=cached['nlp_result'])

        # Configure search
        config = SearchConfig(
            query=search.query,
            mode=SearchMode(search.mode.value),
            words_before=search.words_before,
            words_after=search.words_after,
            fuzzy_threshold=search.fuzzy_threshold,
            max_results=search.max_results
        )

        # Execute search
        results = searcher.search(config)

        # Get statistics
        stats = searcher.get_statistics(results)

        # Build response
        result_responses = [
            SearchResultResponse(
                word_found=r.word_found,
                context_before=r.context_before,
                context_after=r.context_after,
                position=r.position,
                line_number=r.line_number,
                section_ref=r.section_ref,
                lemma=r.lemma,
                pos_tag=r.pos_tag,
                match_score=r.match_score
            )
            for r in results
        ]

        # Word cloud data
        wordcloud_data = [
            {"word": word, "count": count}
            for word, count in stats.context_words
        ]

        return SearchResponse(
            total_occurrences=stats.total_occurrences,
            results=result_responses,
            statistics={
                "total_words": stats.total_words,
                "frequency": stats.frequency,
                "unique_forms": stats.unique_forms,
                "forms_distribution": stats.forms_distribution
            },
            wordcloud_data=wordcloud_data
        )

    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@router.post("/export/html")
async def export_html_report(
    search: SearchRequest,
    cache_key: str = Query(..., description="Cache key from process response"),
    download: bool = Query(True, description="Download as file")
):
    """
    Generate and download an HTML report with highlighted occurrences.

    The report includes:
    - Full text with highlighted matches
    - Statistics and frequency analysis
    - Word cloud of context words
    - Exportable as standalone HTML file
    """
    # Get cached document
    if cache_key not in _document_cache:
        raise HTTPException(
            status_code=404,
            detail="Document not found. Please process the text first"
        )

    cached = _document_cache[cache_key]

    try:
        # Create searcher and search
        searcher = OccurrenceSearcher(document=cached['nlp_result'])

        config = SearchConfig(
            query=search.query,
            mode=SearchMode(search.mode.value),
            words_before=search.words_before,
            words_after=search.words_after,
            fuzzy_threshold=search.fuzzy_threshold
        )

        results = searcher.search(config)

        # Generate HTML report
        generator = HTMLReportGenerator(
            original_text=cached['text'],
            search_results=results,
            config=config,
            document_title=cached.get('title', 'Documento'),
            language=cached.get('language', 'Latino')
        )

        html_content = generator.generate()

        if download:
            # Return as downloadable file
            filename = f"occorrenze_{search.query.replace(' ', '_')}.html"
            return StreamingResponse(
                io.BytesIO(html_content.encode('utf-8')),
                media_type="text/html",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )
        else:
            # Return as response
            return Response(
                content=html_content,
                media_type="text/html"
            )

    except Exception as e:
        logger.error(f"Export error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export error: {str(e)}")


@router.get("/detect-language", response_model=LanguageDetectionResponse)
async def detect_language(
    text: str = Query(..., min_length=10, max_length=10000, description="Text to analyze")
):
    """
    Detect if text is in Latin or Ancient Greek.

    Uses multiple heuristics:
    - Character analysis (Greek Unicode ranges)
    - Stop word identification
    - N-gram frequency patterns

    Returns the detected language with confidence score.
    """
    detector = ClassicalLanguageDetector()
    result = detector.detect(text)

    return LanguageDetectionResponse(
        language=result.language.value,
        confidence=result.confidence,
        greek_char_ratio=result.greek_char_ratio,
        latin_char_ratio=result.latin_char_ratio,
        details=result.details
    )


@router.get("/models", response_model=ModelsResponse)
async def list_available_models():
    """
    List available NLP models for each language.

    Returns information about each model including:
    - Features supported
    - Recommended use cases
    - Description
    """
    models = get_available_models()

    latin_models = [
        ModelInfo(
            id=m['id'],
            name=m['name'],
            description=m['description'],
            features=m['features'],
            recommended_for=m['recommended_for']
        )
        for m in models.get('latin', [])
    ]

    greek_models = [
        ModelInfo(
            id=m['id'],
            name=m['name'],
            description=m['description'],
            features=m['features'],
            recommended_for=m['recommended_for']
        )
        for m in models.get('ancient_greek', [])
    ]

    return ModelsResponse(
        latin=latin_models,
        ancient_greek=greek_models
    )


@router.get("/models/{model_id}")
async def get_model_info(model_id: str):
    """
    Get detailed information about a specific model.
    """
    info = ModelRegistry.get_provider_info(model_id)

    if not info:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found"
        )

    return {
        "id": model_id,
        **info
    }


@router.delete("/cache/{cache_key}")
async def clear_cache_entry(cache_key: str):
    """
    Clear a specific cached document.
    """
    if cache_key in _document_cache:
        del _document_cache[cache_key]
        return {"message": "Cache entry deleted", "cache_key": cache_key}
    else:
        raise HTTPException(status_code=404, detail="Cache entry not found")


@router.get("/cache/stats")
async def get_cache_stats():
    """
    Get cache statistics.
    """
    return {
        "cached_documents": len(_document_cache),
        "cache_keys": list(_document_cache.keys())
    }


@router.post("/botanical/search")
async def search_botanical_terms(
    text: str = Query(..., min_length=1, description="Text to search for botanical terms"),
    language: LanguageEnum = Query(LanguageEnum.AUTO, description="Language of text")
):
    """
    Search for botanical terms in text without full processing.

    Quick endpoint to identify plant-related vocabulary in classical texts.
    Useful for the Virgil/Botanical project.
    """
    # Detect language
    if language == LanguageEnum.AUTO:
        detector = ClassicalLanguageDetector()
        detection = detector.detect(text)
        detected_language = detection.language.value
        if detected_language == "unknown":
            detected_language = "latin"
    else:
        detected_language = language.value

    # Get provider and process
    provider = get_provider_for_language(detected_language)
    await provider.initialize()
    result = await provider.process(text)

    # Extract botanical terms
    botanical_terms = [
        {
            "text": bt.text,
            "lemma": bt.lemma,
            "scientific_name": bt.scientific_name,
            "common_name": bt.common_name,
            "occurrences": bt.occurrences
        }
        for bt in result.botanical_terms
    ]

    return {
        "language": detected_language,
        "total_terms": len(botanical_terms),
        "botanical_terms": botanical_terms
    }


def get_router() -> APIRouter:
    """Get the classical NLP router for integration with main app."""
    return router

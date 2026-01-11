"""
HTML Report Generator for Occurrence Search

Generates standalone HTML reports with:
- Full text with highlighted occurrences
- Statistics and frequency analysis
- Word cloud of context words
- Downloadable format
"""

from typing import List, Dict, Any, Optional
from collections import Counter
from datetime import datetime
import html
import logging

from ..search.config import SearchConfig, SearchResult, SearchMode

logger = logging.getLogger(__name__)


# HTML Template for occurrence report
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Analisi Occorrenze - {{QUERY}}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Palatino Linotype', 'Book Antiqua', Palatino, serif;
            line-height: 1.8;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #fafafa;
            color: #333;
        }

        header {
            background: linear-gradient(135deg, #2c3e50, #34495e);
            color: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 30px;
        }

        h1 { font-size: 1.8em; margin-bottom: 10px; }
        h2 { margin-bottom: 15px; color: #2c3e50; }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }

        .stat-number {
            font-size: 2.5em;
            font-weight: bold;
            color: #3498db;
        }

        .stat-label {
            color: #666;
            font-size: 0.9em;
            margin-top: 5px;
        }

        .text-container {
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            font-size: 1.1em;
            text-align: justify;
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        .highlight {
            background: linear-gradient(180deg, transparent 60%, #ffeb3b 60%);
            padding: 2px 4px;
            border-radius: 3px;
            cursor: pointer;
            transition: background 0.3s;
            position: relative;
        }

        .highlight:hover {
            background: #ffeb3b;
        }

        .highlight[data-index]::after {
            content: attr(data-index);
            position: absolute;
            top: -18px;
            left: 50%;
            transform: translateX(-50%);
            background: #e74c3c;
            color: white;
            font-size: 0.6em;
            padding: 2px 6px;
            border-radius: 10px;
            opacity: 0;
            transition: opacity 0.3s;
        }

        .highlight:hover::after {
            opacity: 1;
        }

        .section {
            margin-top: 30px;
        }

        .occurrences-list {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        .occurrence-item {
            padding: 15px 20px;
            border-bottom: 1px solid #eee;
            display: flex;
            align-items: center;
            gap: 15px;
        }

        .occurrence-item:last-child {
            border-bottom: none;
        }

        .occurrence-number {
            background: #3498db;
            color: white;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            flex-shrink: 0;
        }

        .occurrence-context {
            flex: 1;
        }

        .occurrence-context .word {
            font-weight: bold;
            color: #e74c3c;
        }

        .occurrence-meta {
            font-size: 0.8em;
            color: #666;
        }

        .wordcloud-container {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-top: 30px;
            min-height: 200px;
        }

        .wordcloud {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            align-items: center;
            gap: 10px;
            padding: 20px;
        }

        .wordcloud-word {
            display: inline-block;
            padding: 5px 10px;
            transition: transform 0.3s;
        }

        .wordcloud-word:hover {
            transform: scale(1.1);
        }

        .forms-distribution {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-top: 30px;
        }

        .form-bar {
            display: flex;
            align-items: center;
            margin: 10px 0;
        }

        .form-label {
            width: 150px;
            font-weight: bold;
        }

        .form-bar-fill {
            height: 20px;
            background: linear-gradient(90deg, #3498db, #2980b9);
            border-radius: 3px;
            transition: width 0.5s;
        }

        .form-count {
            margin-left: 10px;
            color: #666;
        }

        footer {
            margin-top: 30px;
            text-align: center;
            color: #666;
            font-size: 0.9em;
            padding: 20px;
        }

        @media print {
            body { background: white; }
            .stat-card, .text-container, .occurrences-list, .wordcloud-container {
                box-shadow: none;
                border: 1px solid #ddd;
            }
            .highlight::after { display: none; }
        }

        @media (max-width: 768px) {
            body { padding: 10px; }
            header { padding: 20px; }
            .text-container { padding: 20px; }
            h1 { font-size: 1.4em; }
        }
    </style>
</head>
<body>
    <header>
        <h1>Analisi Occorrenze</h1>
        <p>Ricerca: <strong>"{{QUERY}}"</strong> | Modalita: {{SEARCH_MODE}}</p>
        <p>Documento: {{DOCUMENT_TITLE}} | Lingua: {{LANGUAGE}}</p>
    </header>

    <!-- Statistiche -->
    <section class="stats-grid">
        <div class="stat-card">
            <div class="stat-number">{{TOTAL_OCCURRENCES}}</div>
            <div class="stat-label">Occorrenze Totali</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{{TOTAL_WORDS}}</div>
            <div class="stat-label">Parole nel Testo</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{{FREQUENCY}}%</div>
            <div class="stat-label">Frequenza</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{{UNIQUE_FORMS}}</div>
            <div class="stat-label">Forme Uniche</div>
        </div>
    </section>

    <!-- Testo Completo con Evidenziazione -->
    <section class="section">
        <h2>Testo con Occorrenze Evidenziate</h2>
        <div class="text-container">
{{HIGHLIGHTED_TEXT}}
        </div>
    </section>

    <!-- Distribuzione Forme -->
    {{FORMS_DISTRIBUTION}}

    <!-- Lista Occorrenze -->
    <section class="section">
        <h2>Elenco Occorrenze</h2>
        <div class="occurrences-list">
{{OCCURRENCES_LIST}}
        </div>
    </section>

    <!-- Word Cloud -->
    <section class="wordcloud-container">
        <h2>Word Cloud - Parole Circostanti</h2>
        <div class="wordcloud">
{{WORDCLOUD_ITEMS}}
        </div>
    </section>

    <footer>
        <p>Generato il {{GENERATION_DATE}} | Sistema NLP/TEI per Testi Classici</p>
        <p>Progetto Botanica-Virgilio</p>
    </footer>
</body>
</html>"""


class HTMLReportGenerator:
    """
    Generates standalone HTML reports for occurrence analysis.

    Features:
    - Full text with highlighted matches
    - Statistics and frequency analysis
    - Interactive word cloud
    - Downloadable standalone HTML
    """

    def __init__(
        self,
        original_text: str,
        search_results: List[SearchResult],
        config: SearchConfig,
        document_title: str = "Documento",
        language: str = "Latino"
    ):
        """
        Initialize the HTML generator.

        Args:
            original_text: The full text to display
            search_results: List of SearchResult objects
            config: SearchConfig used for the search
            document_title: Title of the document
            language: Language of the document
        """
        self.text = original_text
        self.results = search_results
        self.config = config
        self.title = document_title
        self.language = language

    def generate(self) -> str:
        """
        Generate the complete HTML report.

        Returns:
            HTML string
        """
        template = HTML_TEMPLATE

        # Replace placeholders
        replacements = {
            '{{QUERY}}': html.escape(self.config.query),
            '{{SEARCH_MODE}}': self._format_search_mode(),
            '{{DOCUMENT_TITLE}}': html.escape(self.title),
            '{{LANGUAGE}}': self.language,
            '{{TOTAL_OCCURRENCES}}': str(len(self.results)),
            '{{TOTAL_WORDS}}': str(self._count_words()),
            '{{FREQUENCY}}': f"{self._calc_frequency():.2f}",
            '{{UNIQUE_FORMS}}': str(self._count_unique_forms()),
            '{{HIGHLIGHTED_TEXT}}': self._generate_highlighted_text(),
            '{{FORMS_DISTRIBUTION}}': self._generate_forms_distribution(),
            '{{OCCURRENCES_LIST}}': self._generate_occurrences_list(),
            '{{WORDCLOUD_ITEMS}}': self._generate_wordcloud(),
            '{{GENERATION_DATE}}': datetime.now().strftime('%d/%m/%Y %H:%M')
        }

        for key, value in replacements.items():
            template = template.replace(key, value)

        return template

    def _generate_highlighted_text(self) -> str:
        """Generate text with highlighted occurrences."""
        if not self.results:
            return html.escape(self.text)

        # Sort results by position (descending for safe insertion)
        sorted_results = sorted(
            self.results,
            key=lambda r: r.position,
            reverse=True
        )

        highlighted = self.text

        for i, result in enumerate(sorted_results):
            idx = len(self.results) - i  # Occurrence number
            pos = result.position
            word_len = len(result.word_found)

            # Validate position
            if pos < 0 or pos > len(highlighted):
                continue

            # Find the actual word at this position
            end_pos = min(pos + word_len, len(highlighted))

            before = highlighted[:pos]
            word = highlighted[pos:end_pos]
            after = highlighted[end_pos:]

            # Create highlighted span
            highlighted = (
                f'{before}<span class="highlight" data-index="{idx}">'
                f'{html.escape(word)}</span>{after}'
            )

        # Convert newlines to <br> for HTML display
        highlighted = highlighted.replace('\n', '<br>\n')

        return highlighted

    def _generate_forms_distribution(self) -> str:
        """Generate HTML for word forms distribution."""
        if not self.results:
            return ""

        forms = [r.word_found for r in self.results]
        forms_counter = Counter(forms)
        max_count = max(forms_counter.values()) if forms_counter else 1

        if len(forms_counter) <= 1:
            return ""

        html_parts = [
            '<section class="forms-distribution">',
            '<h2>Distribuzione Forme</h2>'
        ]

        for form, count in forms_counter.most_common(10):
            width = (count / max_count) * 100
            html_parts.append(f'''
            <div class="form-bar">
                <span class="form-label">{html.escape(form)}</span>
                <div class="form-bar-fill" style="width: {width}%;"></div>
                <span class="form-count">{count}</span>
            </div>
            ''')

        html_parts.append('</section>')
        return '\n'.join(html_parts)

    def _generate_occurrences_list(self) -> str:
        """Generate HTML list of occurrences with context."""
        items = []

        for i, result in enumerate(self.results, 1):
            meta_parts = [f'Riga {result.line_number}']

            if result.section_ref:
                meta_parts.append(result.section_ref)
            if result.lemma:
                meta_parts.append(f'Lemma: {result.lemma}')
            if result.pos_tag:
                meta_parts.append(f'POS: {result.pos_tag}')

            items.append(f'''
            <div class="occurrence-item">
                <div class="occurrence-number">{i}</div>
                <div class="occurrence-context">
                    {html.escape(result.context_before)}
                    <span class="word">{html.escape(result.word_found)}</span>
                    {html.escape(result.context_after)}
                </div>
                <div class="occurrence-meta">
                    {' | '.join(meta_parts)}
                </div>
            </div>
            ''')

        return '\n'.join(items)

    def _generate_wordcloud(self) -> str:
        """Generate HTML word cloud from context words."""
        # Collect context words
        context_words = []

        for result in self.results:
            words = result.context_before.split() + result.context_after.split()
            context_words.extend([
                w.lower().strip('.,;:!?()[]"\'')
                for w in words
                if len(w) > 2
            ])

        # Count frequencies
        word_freq = Counter(context_words)

        if not word_freq:
            return '<span class="wordcloud-word">Nessun contesto disponibile</span>'

        max_freq = max(word_freq.values())

        # Generate HTML
        items = []
        for word, freq in word_freq.most_common(50):
            # Calculate font size (1em - 3em based on frequency)
            size = 1 + (freq / max_freq) * 2

            # Color based on frequency (blue to purple spectrum)
            hue = 200 + (freq / max_freq) * 60

            items.append(
                f'<span class="wordcloud-word" style="font-size: {size:.1f}em; '
                f'color: hsl({hue:.0f}, 60%, 45%);">{html.escape(word)}</span>'
            )

        return '\n'.join(items)

    def _count_words(self) -> int:
        """Count total words in text."""
        return len(self.text.split())

    def _calc_frequency(self) -> float:
        """Calculate occurrence frequency percentage."""
        total = self._count_words()
        if total == 0:
            return 0.0
        return len(self.results) / total * 100

    def _count_unique_forms(self) -> int:
        """Count unique word forms in results."""
        return len(set(r.word_found.lower() for r in self.results))

    def _format_search_mode(self) -> str:
        """Format search mode for display."""
        modes = {
            SearchMode.EXACT: "Ricerca Esatta",
            SearchMode.LEMMATIZED: "Ricerca Lemmatizzata",
            SearchMode.REGEX: "Espressione Regolare",
            SearchMode.FUZZY: "Ricerca Fuzzy"
        }
        return modes.get(self.config.mode, "N/A")


def generate_occurrence_report(
    text: str,
    results: List[SearchResult],
    config: SearchConfig,
    title: str = "Documento",
    language: str = "Latino"
) -> str:
    """
    Convenience function to generate an HTML occurrence report.

    Args:
        text: Full document text
        results: Search results
        config: Search configuration
        title: Document title
        language: Document language

    Returns:
        HTML string
    """
    generator = HTMLReportGenerator(
        original_text=text,
        search_results=results,
        config=config,
        document_title=title,
        language=language
    )
    return generator.generate()

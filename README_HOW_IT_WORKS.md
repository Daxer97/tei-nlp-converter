# Architettura e Workflow dell'Applicazione TEI NLP Converter

## **Panoramica del Sistema**

Il TEI NLP Converter è un'applicazione web che trasforma il testo semplice in documenti TEI XML semanticamente ricchi utilizzando il Natural Language Processing. Ecco come i dati fluiscono attraverso il sistema:

```
Testo Semplice → Elaborazione NLP → Dati Strutturati → Conversione TEI → Documento TEI XML
```

---

## **Componenti Principali e i Loro Ruoli**

### 1. **Livello di Elaborazione NLP**
Il componente NLP estrae informazioni linguistiche e semantiche dal testo grezzo:

**Input**: Stringa di testo semplice  
**Output**: JSON strutturato con annotazioni linguistiche

```python
# Da nlp_connector.py
{
    "sentences": [...],      # Confini delle frasi
    "entities": [...],       # Entità nominate (persone, luoghi, organizzazioni)
    "tokens": [...],        # Singole parole con proprietà linguistiche
    "dependencies": [...],   # Relazioni sintattiche tra parole
    "noun_chunks": [...],   # Sintagmi nominali
    "language": "en"
}
```

Il sistema supporta **modelli NLP domain-specific**:
- **SpaCy** (elaborazione locale con modelli specializzati)
- **Domain-Specific Models** (BioBERT, Legal-BERT, SciSpaCy)
- **Server NLP Remoto** (deployment personalizzato)

**NOTA**: Google Cloud NLP è stato deprecato e rimosso a favore di modelli NER locali domain-specific che offrono maggiore accuratezza per domini specializzati.

### 2. **Livello di Conversione TEI**
Trasforma l'output NLP in formato TEI XML basato su schemi specifici per dominio.

---

## **Pipeline di Elaborazione Dettagliata**

### **Passo 1: Ricezione del Testo**
```python
# app.py - Punto di ingresso
@app.post("/process")
async def process_text(request: TextProcessRequest):
    # Valida il testo di input (max 100.000 caratteri)
    # Seleziona lo schema del dominio (letterario, storico, legale, ecc.)
```

### **Passo 2: Analisi NLP**
```python
# nlp_connector.py
async def process(self, text: str, options: ProcessingOptions):
    # 1. Tokenizzazione: Divide il testo in parole
    # 2. Tagging Part-of-Speech: Identifica i tipi di parole (sostantivo, verbo, ecc.)
    # 3. Riconoscimento Entità Nominate: Trova persone, luoghi, organizzazioni
    # 4. Parsing delle Dipendenze: Analizza la struttura grammaticale
    # 5. Lemmatizzazione: Estrae le forme base delle parole
```

**Esempio di Output NLP**:
```json
{
  "sentences": [
    {
      "text": "Giovanni Rossi ha visitato Parigi l'estate scorsa.",
      "tokens": [
        {"text": "Giovanni", "pos": "PROPN", "lemma": "Giovanni", "dep": "nsubj"},
        {"text": "Rossi", "pos": "PROPN", "lemma": "Rossi", "dep": "flat"},
        {"text": "visitato", "pos": "VERB", "lemma": "visitare", "dep": "ROOT"},
        {"text": "Parigi", "pos": "PROPN", "lemma": "Parigi", "dep": "dobj"}
      ]
    }
  ],
  "entities": [
    {"text": "Giovanni Rossi", "label": "PERSON", "start": 0, "end": 2},
    {"text": "Parigi", "label": "GPE", "start": 3, "end": 4}
  ]
}
```

### **Passo 3: Conversione TEI**
La classe `TEIConverter` trasforma i dati NLP in TEI XML utilizzando regole specifiche per dominio:

```python
# tei_converter.py
def convert(self, text: str, nlp_results: Dict) -> str:
    # Crea struttura TEI con:
    # - Header (metadati, informazioni di codifica)
    # - Body (testo annotato)
    # - Annotazioni standoff (opzionali)
```

**Tre Strategie di Annotazione**:

1. **Inline** - Annotazioni incorporate nel testo:
```xml
<s>
  <persName>Giovanni Rossi</persName> ha visitato 
  <placeName>Parigi</placeName> l'estate scorsa.
</s>
```

2. **Standoff** - Annotazioni separate dal testo:
```xml
<text>
  <body>
    <p id="p1">Giovanni Rossi ha visitato Parigi l'estate scorsa.</p>
  </body>
  <standOff>
    <listAnnotation>
      <annotation target="#char_0_13" type="person">Giovanni Rossi</annotation>
      <annotation target="#char_27_33" type="place">Parigi</annotation>
    </listAnnotation>
  </standOff>
</text>
```

3. **Misto** - Combinazione di entrambi gli approcci

### **Passo 4: Schemi Specifici per Dominio**
Il `OntologyManager` fornisce schemi specializzati per diversi domini:

| Dominio | Caratteristiche Speciali | Mappature di Entità |
|---------|-------------------------|----------------------|
| **Letterario** | Analisi dei personaggi, citazioni, dialoghi | CHARACTER → persName |
| **Storico** | Date, eventi, provenienza | EVENT → event |
| **Legale** | Clausole, disposizioni, statuti | LAW → name, COURT → orgName |
| **Scientifico** | Formule, misurazioni, citazioni | CHEMICAL → term |
| **Linguistico** | Analisi dettagliata dei token, morfologia | Annotazione linguistica completa |

---

## **Esempio di Workflow Completo**

**Testo di Input**: "Shakespeare scrisse Amleto nel 1600."

**1. Elaborazione NLP**:
```json
{
  "entities": [
    {"text": "Shakespeare", "label": "PERSON"},
    {"text": "Amleto", "label": "WORK_OF_ART"},
    {"text": "1600", "label": "DATE"}
  ]
}
```

**2. Selezione Schema del Dominio** (Letterario):
```python
schema = {
    "domain": "literary",
    "entity_mappings": {
        "PERSON": "persName",
        "WORK_OF_ART": "title"
    }
}
```

**3. Output TEI XML**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>Analisi Letteraria</title>
      </titleStmt>
      <encodingDesc>
        <tagsDecl>
          <namespace name="http://www.tei-c.org/ns/1.0">
            <tagUsage gi="persName" occurs="1"/>
            <tagUsage gi="title" occurs="1"/>
            <tagUsage gi="date" occurs="1"/>
          </namespace>
        </tagsDecl>
      </encodingDesc>
    </fileDesc>
  </teiHeader>
  <text>
    <body>
      <div type="chapter">
        <s>
          <persName ref="#Shakespeare">Shakespeare</persName> scrisse 
          <title type="literary">Amleto</title> nel 
          <date when="1600">1600</date>.
        </s>
      </div>
    </body>
  </text>
</TEI>
```

---

## **Caratteristiche Principali**

### **Ottimizzazione delle Prestazioni**
- **Caching**: Risultati memorizzati in Redis/memoria per evitare rielaborazioni
- **Elaborazione in Background**: Testi lunghi elaborati in modo asincrono
- **Circuit Breaker**: Previene guasti a cascata nei servizi NLP

### **Scalabilità**
- **Fallback del Provider**: Failover automatico tra provider NLP
- **Scaling Orizzontale**: Deployment Kubernetes con auto-scaling
- **Bilanciamento del Carico**: Processi worker multipli

### **Persistenza dei Dati**
- Testi elaborati memorizzati in PostgreSQL/SQLite
- Logging di audit per conformità
- Politiche di conservazione configurabili

---

## **Perché il Formato TEI?**

TEI (Text Encoding Initiative) è lo standard de facto per le discipline umanistiche digitali perché:
1. **Preserva il significato semantico** insieme al testo
2. **Abilita l'analisi accademica** attraverso markup strutturato
3. **Supporta l'interoperabilità** tra strumenti di ricerca
4. **Mantiene la leggibilità umana** pur essendo elaborabile dalle macchine
5. **Fornisce vocabolari specifici per dominio** per diversi campi

Il livello NLP arricchisce questo identificando e marcando automaticamente caratteristiche linguistiche e semantiche che richiederebbero molto tempo per essere annotate manualmente.

# Come il TEI Ontology Manager Mappa l'Output NLP Dinamico alla Struttura TEI

## **La Sfida della Mappatura**

Il sistema deve collegare due strutture dati diverse:
- **Output NLP**: Struttura piatta, basata su liste con entità, token, dipendenze
- **TEI XML**: Struttura gerarchica ad albero, specifica per dominio con markup semantico

Il `OntologyManager` e il `TEIConverter` lavorano insieme per creare questa mappatura dinamica attraverso un **processo di trasformazione guidato da schema**.

---

## **Il Meccanismo di Mappatura**

### **1. Schema come Blueprint di Traduzione**

Ogni schema di dominio agisce come una configurazione di mappatura che dice al convertitore:
- Quali campi NLP cercare
- Come trasformarli in elementi TEI
- Dove posizionarli nella gerarchia XML

```python
# Da ontology_manager.py - Struttura dello schema
schema = {
    "entity_mappings": {         # Etichetta NLP → elemento TEI
        "PERSON": "persName",
        "LOC": "placeName",
        "ORG": "orgName"
    },
    "annotation_strategy": "inline",  # Come incorporare le annotazioni
    "include_pos": True,              # Quali caratteristiche NLP utilizzare
    "include_lemma": True,
    "include_dependencies": True
}
```

### **2. Processo di Mappatura Dinamica dei Campi**

Il `TEIConverter` esegue **lookup basati su chiavi** nei risultati NLP:

```python
# Semplificato da tei_converter.py
def _add_inline_annotations(self, body, nlp_results):
    # 1. Controlla se NLP ha entità
    if 'entities' in nlp_results and nlp_results['entities']:
        entity_map = self._build_entity_map(nlp_results['entities'])
        
    # 2. Controlla se NLP ha frasi
    if 'sentences' in nlp_results:
        for sentence in nlp_results['sentences']:
            # 3. Controlla se la frase ha token
            if 'tokens' in sentence:
                self._process_tokens(sentence['tokens'])
```

---

## **Flusso di Mappatura Dettagliato**

### **Passo 1: Ispezione dei Risultati NLP**
Il convertitore prima **valida e ispeziona** ciò che l'NLP ha effettivamente fornito:

```python
def _validate_nlp_results(self, nlp_results):
    # Controlla dinamicamente quali campi esistono
    available_fields = {
        'has_sentences': 'sentences' in nlp_results,
        'has_entities': 'entities' in nlp_results,
        'has_dependencies': 'dependencies' in nlp_results,
        'has_tokens': any('tokens' in s for s in nlp_results.get('sentences', []))
    }
```

### **Passo 2: Selezione Guidata da Schema**
Basandosi sullo schema, **elabora selettivamente** i dati NLP disponibili:

```python
# Lo schema controlla ciò che viene convertito
if self.schema.get('include_entities', True) and 'entities' in nlp_results:
    # Elabora entità
    
if self.schema.get('include_dependencies', False) and 'dependencies' in nlp_results:
    # Elabora dipendenze
```

### **Passo 3: Creazione Dinamica di Elementi**
Gli elementi TEI vengono creati basandosi su **mappature etichetta NLP → elemento TEI**:

```python
def _create_entity_element(self, entity):
    # Cerca l'etichetta NLP nella tabella di mappatura
    entity_type = entity['label']  # es., "PERSON"
    
    # Trova l'elemento TEI corrispondente
    tei_element = self.entity_mappings.get(
        entity_type,                              # Prova corrispondenza esatta
        self.entity_mappings.get('DEFAULT', 'name')  # Fallback
    )
    
    # Crea l'elemento XML appropriato
    elem = ET.Element(f'{TEI_NAMESPACE}{tei_element}')
```

---

## **Esempio Concreto: Mappatura Dinamica**

Tracciamo come diversi output NLP si mappano a TEI:

### **Scenario 1: Output NLP Completo**
```python
nlp_results = {
    "entities": [{"text": "Einstein", "label": "PERSON"}],
    "sentences": [{"tokens": [...], "text": "..."}],
    "dependencies": [{"from": 0, "to": 1, "dep": "nsubj"}]
}
```

**Output TEI** (con schema letterario):
```xml
<persName>Einstein</persName>  <!-- entità mappata -->
<w lemma="Einstein" pos="PROPN">Einstein</w>  <!-- token mappato -->
<!-- dipendenze incluse in standoff -->
```

### **Scenario 2: Output NLP Parziale**
```python
nlp_results = {
    "entities": [{"text": "Parigi", "label": "LOC"}],
    # Nessuna dipendenza fornita dall'NLP
}
```

**Output TEI**:
```xml
<placeName>Parigi</placeName>  <!-- Solo entità mappate -->
<!-- Nessuna annotazione di dipendenza poiché l'NLP non le ha fornite -->
```

---

## **Strategie di Mappatura Adattive**

### **1. Inclusione Basata sulla Presenza**
Il convertitore include solo elementi TEI per **dati che esistono**:

```python
# Da tei_converter.py
if nlp_results.get('noun_chunks'):  # Solo se NLP ha fornito noun chunks
    self._add_noun_chunk_annotations(...)
```

### **2. Normalizzazione delle Etichette**
Diversi provider NLP usano etichette diverse. Il sistema le **normalizza**:

```python
def normalize_entity_type(self, provider_type):
    mappings = {
        "PERSON": "PERSON",      # SpaCy
        "PER": "PERSON",         # Alcuni modelli
        "LOCATION": "LOC",       # Google
        "GPE": "LOC",           # Entità geopolitiche
    }
    return mappings.get(provider_type, provider_type)
```

### **3. Gestione dei Fallback**
Quando i dati NLP sono mancanti o incompleti:

```python
def _create_fallback_tei(self, text, error):
    # Crea TEI minimo valido senza annotazioni NLP
    return f"""
    <TEI>
        <text>
            <body>
                <p>{escaped_text}</p>  <!-- Solo il testo, nessuna annotazione -->
            </body>
        </text>
    </TEI>
    """
```

---

## **Adattamenti Specifici per Dominio**

Diversi domini **danno priorità a diverse caratteristiche NLP**:

| Dominio | Caratteristiche NLP Utilizzate | Elementi TEI Creati |
|---------|--------------------------------|---------------------|
| **Letterario** | Entità, POS, Dipendenze | `<persName>`, `<quote>`, `<said>` |
| **Legale** | Solo entità | `<orgName>`, `<name type="law">` |
| **Linguistico** | Dettagli completi dei token, morfologia | `<w>`, `<pc>`, `<c>`, caratteristiche morfologiche |
| **Storico** | Entità, Date | `<date>`, `<event>`, `<placeName>` |

Lo schema determina questo attraverso flag:
```python
"legal": {
    "include_pos": False,        # Non servono tag POS
    "include_dependencies": False, # Non servono alberi sintattici
    "include_entities": True      # Interessano solo le entità
}
```

---

## **Principi Chiave del Design**

1. **Degradazione Elegante**: I dati NLP mancanti non interrompono la conversione
2. **Guidato da Schema**: Lo schema del dominio controlla ciò che viene mappato
3. **Agnostico del Provider**: Funziona con il formato di output di qualsiasi provider NLP
4. **Elaborazione Selettiva**: Elabora solo ciò che è necessario e disponibile
5. **Sicurezza di Fallback**: Produce sempre TEI valido, anche con dati minimi

Il sistema non richiede che l'NLP fornisca tutti i campi possibili - si **adatta dinamicamente** a qualsiasi cosa produca l'analisi NLP, guidato dallo schema del dominio per creare markup TEI appropriato.

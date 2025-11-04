# Google Cloud NLP Integration Guide

This guide explains how to set up and use the Google Cloud Natural Language API with the TEI NLP Converter for superior text analysis capabilities.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Google Cloud Setup](#google-cloud-setup)
4. [Configuration](#configuration)
5. [Features](#features)
6. [Usage Examples](#usage-examples)
7. [Troubleshooting](#troubleshooting)
8. [Best Practices](#best-practices)

## Overview

The Google Cloud NLP integration provides advanced text analysis capabilities including:

- **Entity Salience**: Importance scoring for entities
- **Entity Sentiment**: Emotional context for each entity
- **Knowledge Graph**: Wikipedia URLs and Knowledge Graph MIDs
- **Rich Morphology**: Detailed grammatical features
- **Superior Accuracy**: Higher precision for entity recognition
- **Multi-language Support**: Better language detection

## Prerequisites

- Google Cloud Platform (GCP) account
- Google Cloud project with billing enabled
- Natural Language API enabled
- Service account with appropriate permissions

## Google Cloud Setup

### Step 1: Create a Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Select a Project" → "New Project"
3. Enter a project name (e.g., "tei-nlp-converter")
4. Click "Create"

### Step 2: Enable the Natural Language API

1. Navigate to "APIs & Services" → "Library"
2. Search for "Cloud Natural Language API"
3. Click on it and press "Enable"

### Step 3: Create Service Account Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "Service Account"
3. Fill in the service account details:
   - Name: `tei-nlp-service`
   - ID: `tei-nlp-service`
   - Description: "Service account for TEI NLP Converter"
4. Click "Create and Continue"
5. Grant the role: "Cloud Natural Language API User"
6. Click "Continue" → "Done"

### Step 4: Generate and Download Key

1. Click on the created service account
2. Go to "Keys" tab
3. Click "Add Key" → "Create New Key"
4. Select "JSON" format
5. Click "Create" - the key file will download automatically
6. **IMPORTANT**: Store this file securely - it contains sensitive credentials

### Step 5: Secure the Credentials File

```bash
# Move the credentials file to your project directory
mv ~/Downloads/[PROJECT_ID]-[KEY_ID].json ./google-credentials.json

# Set proper permissions (read-only for owner)
chmod 600 google-credentials.json

# Verify permissions
ls -la google-credentials.json
# Should show: -rw------- (600)
```

## Configuration

### Option 1: Environment Variables

Create or update your `.env` file:

```bash
# Copy the example file
cp .env.example .env

# Edit the .env file with your settings
nano .env
```

Add the following configuration:

```env
# NLP Provider Configuration
NLP_PROVIDER=google
NLP_FALLBACK_PROVIDERS=spacy

# Google Cloud Configuration
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/google-credentials.json

# Optional: API quotas and limits
GOOGLE_API_RATE_LIMIT=600
GOOGLE_API_QUOTA_DAILY=800000
GOOGLE_API_MAX_TEXT_LENGTH=1000000
```

### Option 2: Docker Configuration

Update your `docker-compose.yml`:

```yaml
services:
  web:
    environment:
      - NLP_PROVIDER=google
      - GOOGLE_CLOUD_PROJECT=your-project-id
      - GOOGLE_APPLICATION_CREDENTIALS=/app/google-credentials.json
    volumes:
      - /path/to/your/google-credentials.json:/app/google-credentials.json:ro
```

### Option 3: Application Default Credentials

For development, you can use ADC:

```bash
# Install Google Cloud SDK
# https://cloud.google.com/sdk/docs/install

# Authenticate
gcloud auth application-default login

# Set project
gcloud config set project YOUR_PROJECT_ID
```

## Features

### Entity Salience

Google Cloud NLP provides salience scores (0.0 to 1.0) indicating entity importance:

```python
# Entities are automatically sorted by salience
{
  "entities": [
    {
      "text": "Google",
      "label": "ORG",
      "salience": 0.85,  # High importance
      ...
    },
    {
      "text": "yesterday",
      "label": "DATE",
      "salience": 0.15,  # Low importance
      ...
    }
  ]
}
```

**TEI Output**:
```xml
<orgName ana="#salience-high" ref="https://en.wikipedia.org/wiki/Google">Google</orgName>
<date ana="#salience-low">yesterday</date>
```

### Entity Sentiment

Each entity includes sentiment analysis:

```python
{
  "text": "Apple",
  "label": "ORG",
  "sentiment": {
    "score": 0.6,      # -1 (negative) to +1 (positive)
    "magnitude": 0.9   # 0 (low) to infinity (high intensity)
  }
}
```

**TEI Output**:
```xml
<orgName sentiment="positive">Apple</orgName>
```

### Knowledge Graph Integration

Entities are linked to external knowledge bases:

```python
{
  "text": "Paris",
  "label": "LOC",
  "metadata": {
    "wikipedia_url": "https://en.wikipedia.org/wiki/Paris",
    "knowledge_graph_mid": "/m/05qtj"
  }
}
```

**TEI Output**:
```xml
<placeName
  ref="https://en.wikipedia.org/wiki/Paris"
  corresp="https://www.google.com/kg/mid/m/05qtj">
  Paris
</placeName>
```

### Provider-Aware Entity Mappings

Google-specific entity types are properly mapped to TEI elements:

| Google Entity Type | TEI Element | Example |
|--------------------|-------------|---------|
| PERSON | persName | `<persName>John Doe</persName>` |
| LOCATION | placeName | `<placeName>New York</placeName>` |
| ORGANIZATION | orgName | `<orgName>Google</orgName>` |
| PHONE_NUMBER | num | `<num type="phone">555-1234</num>` |
| ADDRESS | address | `<address>123 Main St</address>` |
| DATE | date | `<date>January 1, 2024</date>` |
| PRICE | measure | `<measure type="currency">$99.99</measure>` |
| WORK_OF_ART | title | `<title>Mona Lisa</title>` |
| CONSUMER_GOOD | objectName | `<objectName>iPhone</objectName>` |

## Usage Examples

### Basic Usage with Python API

```python
from nlp_connector import NLPProcessor
from tei_converter import TEIConverter
from ontology_manager import OntologyManager

# Initialize components
processor = NLPProcessor(
    primary_provider='google',
    fallback_providers=['spacy']
)
await processor.initialize_providers()

ontology_manager = OntologyManager()
schema = ontology_manager.get_schema('legal')

# Process text
text = "Apple Inc. announced a new product yesterday."
nlp_results = await processor.process(text)

# Convert to TEI with Google-specific features
converter = TEIConverter(
    schema=schema,
    provider_name='google',
    ontology_manager=ontology_manager
)
tei_xml = converter.convert(text, nlp_results)
```

### REST API Usage

```bash
# Process text with Google Cloud NLP
curl -X POST "http://localhost:8080/convert" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Google was founded in California by Larry Page.",
    "domain": "historical",
    "options": {
      "include_sentiment": true
    }
  }'
```

### Optimal Provider Selection

The system can automatically select the best provider based on your needs:

```python
from ontology_manager import OntologyManager

ontology_manager = OntologyManager()

# Legal documents → Google (for precision)
provider = ontology_manager.select_optimal_provider(
    text="This agreement shall be governed...",
    domain="legal"
)
# Returns: 'google'

# Very long texts → SpaCy (local processing)
long_text = "word " * 100000
provider = ontology_manager.select_optimal_provider(
    text=long_text,
    domain="default"
)
# Returns: 'spacy'

# Linguistic analysis → SpaCy (rich morphology)
provider = ontology_manager.select_optimal_provider(
    text="Analyzing grammatical structures...",
    domain="linguistic"
)
# Returns: 'spacy'
```

## Troubleshooting

### Common Issues

#### 1. Authentication Errors

**Error**: `DefaultCredentialsError: Could not automatically determine credentials`

**Solution**:
```bash
# Check if credentials file exists
ls -la /path/to/google-credentials.json

# Verify GOOGLE_APPLICATION_CREDENTIALS is set
echo $GOOGLE_APPLICATION_CREDENTIALS

# Test credentials
gcloud auth application-default login
```

#### 2. Permission Denied

**Error**: `PermissionDenied: The caller does not have permission`

**Solution**:
- Ensure the service account has "Cloud Natural Language API User" role
- Check if the API is enabled in your project
- Verify billing is enabled

#### 3. Quota Exceeded

**Error**: `ResourceExhausted: Quota exceeded`

**Solution**:
- The system automatically falls back to SpaCy
- Check your quota in Google Cloud Console → APIs & Services → Quotas
- Request quota increase if needed
- Implement rate limiting in your application

#### 4. Invalid Credentials File

**Error**: `ValueError: Invalid service account file`

**Solution**:
```bash
# Verify JSON file is valid
cat google-credentials.json | jq .

# Check file permissions
ls -la google-credentials.json

# Re-download the credentials if corrupted
```

### Checking Provider Status

```python
# Get status of all providers
processor = await get_nlp_processor()
status = await processor.get_provider_status()

print(status)
# {
#   "primary": "google",
#   "fallbacks": ["spacy"],
#   "provider_status": {
#     "google": "available",
#     "spacy": "available"
#   }
# }
```

### Monitoring and Logs

Check application logs for Google Cloud NLP activity:

```bash
# View logs
tail -f logs/app.log | grep -i google

# Look for these messages:
# - "Google Cloud NLP initialized successfully"
# - "Applied Google Cloud NLP conversion strategy"
# - "Enabled sentiment analysis for Google Cloud NLP"
```

## Best Practices

### 1. Security

- **Never commit credentials files to version control**
- Add `google-credentials.json` to `.gitignore`
- Use environment variables for sensitive data
- Rotate service account keys regularly
- Use separate service accounts for dev/staging/prod

```bash
# .gitignore
google-credentials.json
*.json
!package.json
!tsconfig.json
```

### 2. Cost Optimization

- **Use caching**: Results are cached automatically (configurable TTL)
- **Implement fallback**: SpaCy processes locally when quota exceeded
- **Batch processing**: Process multiple texts in one session
- **Monitor usage**: Set up billing alerts in Google Cloud Console

```python
# Cache configuration
CACHE_TTL=3600  # Cache results for 1 hour
```

### 3. Performance

- **Text length**: Keep texts under 100KB for optimal performance
- **Concurrent requests**: Google has rate limits (600 req/min default)
- **Connection pooling**: Reuse NLP processor instances
- **Async processing**: Use background tasks for large batches

### 4. Fallback Strategy

Always configure fallback providers:

```env
# Recommended fallback chain
NLP_PROVIDER=google
NLP_FALLBACK_PROVIDERS=spacy

# The system will:
# 1. Try Google Cloud NLP first
# 2. Fall back to SpaCy if Google fails
# 3. Continue processing without interruption
```

### 5. Domain-Specific Optimization

Different domains benefit from different providers:

| Domain | Recommended Provider | Reason |
|--------|---------------------|--------|
| Legal | Google | Higher precision, entity sentiment |
| Scientific | Google | Better entity recognition, knowledge graph |
| Historical | Google | Entity salience, better date handling |
| Literary | SpaCy | Rich morphology, local processing |
| Linguistic | SpaCy | Detailed dependency parsing |
| Long texts (>100KB) | SpaCy | No API limits, faster for large texts |

## API Quotas and Limits

### Free Tier

- **5,000 text records** per month free
- 1,000 text characters per text record
- After free tier: $1.00 per 1,000 text records

### Limits

- **Text size**: 1,000,000 characters per request
- **Rate limit**: 600 requests per minute (configurable)
- **Daily quota**: 800,000 characters per day (default)

### Monitoring Usage

```bash
# View usage in Google Cloud Console
https://console.cloud.google.com/apis/api/language.googleapis.com/quotas

# Set up billing alerts
https://console.cloud.google.com/billing/alerts
```

## Support and Resources

### Official Documentation

- [Google Cloud Natural Language API](https://cloud.google.com/natural-language/docs)
- [Client Libraries](https://cloud.google.com/natural-language/docs/reference/libraries)
- [Pricing](https://cloud.google.com/natural-language/pricing)

### TEI NLP Converter Resources

- [Main README](README.md)
- [Architecture Documentation](README_STRUCT.md)
- [How It Works](README_HOW_IT_WORKS.md)

### Getting Help

- GitHub Issues: [Report issues](https://github.com/your-repo/issues)
- Documentation: Check README files in the repository
- Logs: Always check `logs/app.log` for detailed error messages

## Example: Complete Setup Walkthrough

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up Google Cloud credentials
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/google-credentials.json"
export GOOGLE_CLOUD_PROJECT="your-project-id"

# 3. Configure environment
cat > .env << EOF
NLP_PROVIDER=google
NLP_FALLBACK_PROVIDERS=spacy
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/google-credentials.json
EOF

# 4. Test the setup
python << PYTHON
import asyncio
from nlp_connector import NLPProcessor

async def test():
    processor = NLPProcessor(primary_provider='google')
    await processor.initialize_providers()
    result = await processor.process("Google is a technology company.")
    print("Success! Entities:", result['entities'])

asyncio.run(test())
PYTHON

# 5. Start the application
uvicorn app:app --host 0.0.0.0 --port 8080
```

## Conclusion

The Google Cloud NLP integration provides state-of-the-art text analysis capabilities with seamless fallback to local processing. Follow this guide to set up and optimize your TEI NLP Converter for maximum performance and accuracy.

For questions or issues, please refer to the troubleshooting section or check the application logs.
